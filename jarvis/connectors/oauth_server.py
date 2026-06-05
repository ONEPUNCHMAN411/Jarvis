"""
Lightweight localhost OAuth callback server for Google APIs.

Security measures:
- state parameter (CSRF protection per RFC 6749 §10.12)
- client_secret never written to the token file
- Token file ACL restricted to current user only
"""

import asyncio
import json
import os
import secrets
import subprocess
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from loguru import logger

_REDIRECT_PORT = 8914
_REDIRECT_URI = f"http://localhost:{_REDIRECT_PORT}"


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handles the OAuth redirect and captures the authorization code."""

    auth_code: str | None = None
    error: str | None = None
    expected_state: str | None = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        received_state = params.get("state", [None])[0]
        if received_state != _OAuthCallbackHandler.expected_state:
            _OAuthCallbackHandler.error = "state_mismatch"
            self._respond(
                400,
                "<html><body style='background:#020617;color:#FB7185;font-family:Segoe UI;"
                "text-align:center;padding-top:80px'>"
                "<h1>Authorization failed</h1><p>Invalid state parameter (CSRF check failed).</p>"
                "</body></html>",
            )
            return

        if "code" in params:
            _OAuthCallbackHandler.auth_code = params["code"][0]
            self._respond(
                200,
                "<html><body style='background:#020617;color:#00E5FF;font-family:Segoe UI;"
                "text-align:center;padding-top:80px'>"
                "<h1>&#x2714; Authorization successful</h1>"
                "<p style='color:#94A3B8'>You can close this tab and return to JARVIS.</p>"
                "</body></html>",
            )
        elif "error" in params:
            _OAuthCallbackHandler.error = params["error"][0]
            self._respond(
                400,
                "<html><body style='background:#020617;color:#FB7185;font-family:Segoe UI;"
                "text-align:center;padding-top:80px'>"
                f"<h1>Authorization failed</h1><p>{_OAuthCallbackHandler.error}</p>"
                "</body></html>",
            )
        else:
            self._respond(400, "Missing code parameter")

    def _respond(self, status: int, body: str):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        logger.debug(f"OAuth callback: {format % args}")


def _exchange_code_for_token(
    client_id: str,
    client_secret: str,
    code: str,
    scopes: list[str],
) -> dict:
    """Exchange authorization code for access/refresh tokens."""
    import urllib.request
    import urllib.parse

    data = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": _REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _restrict_file_to_user(path: str) -> None:
    """Set token file ACL to current user only (Windows)."""
    try:
        username = os.environ.get("USERNAME") or os.getlogin()
        subprocess.run(
            ["icacls", path, "/inheritance:r", "/grant:r", f"{username}:F"],
            capture_output=True, timeout=10,
        )
    except Exception as e:
        logger.warning(f"Failed to restrict token file permissions: {e}")


async def run_google_oauth(
    credentials_json_path: str,
    scopes: list[str],
    token_output_path: str | None = None,
) -> str | None:
    """
    Run the Google OAuth flow with CSRF state validation.
    Saves access_token, refresh_token, and scopes — but NOT client_secret.
    Returns the path to the token file, or None on failure.
    """
    creds_path = Path(credentials_json_path)
    if not creds_path.exists():
        logger.error(f"Credentials file not found: {credentials_json_path}")
        return None

    try:
        with open(creds_path, "r", encoding="utf-8") as f:
            creds_data = json.load(f)
    except Exception as exc:
        logger.error(f"Failed to read credentials.json: {exc}")
        return None

    app_data = creds_data.get("installed") or creds_data.get("web")
    if not app_data:
        logger.error("Invalid credentials.json — missing 'installed' or 'web' key")
        return None

    client_id = app_data["client_id"]
    client_secret = app_data["client_secret"]
    auth_uri = app_data.get("auth_uri", "https://accounts.google.com/o/oauth2/auth")

    # Generate a cryptographically random state value for CSRF protection
    csrf_state = secrets.token_urlsafe(32)

    _OAuthCallbackHandler.auth_code = None
    _OAuthCallbackHandler.error = None
    _OAuthCallbackHandler.expected_state = csrf_state

    import urllib.parse
    auth_params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": _REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": csrf_state,
    })
    auth_url = f"{auth_uri}?{auth_params}"

    server = HTTPServer(("localhost", _REDIRECT_PORT), _OAuthCallbackHandler)
    server.timeout = 120

    def _serve():
        server.handle_request()

    server_thread = threading.Thread(target=_serve, daemon=True)
    server_thread.start()

    logger.info("Opening browser for Google OAuth consent…")
    webbrowser.open(auth_url)

    await asyncio.to_thread(server_thread.join, timeout=120)

    try:
        server.server_close()
    except Exception:
        pass

    if _OAuthCallbackHandler.error:
        logger.error(f"OAuth error: {_OAuthCallbackHandler.error}")
        return None

    if not _OAuthCallbackHandler.auth_code:
        logger.error("OAuth timed out — no authorization code received")
        return None

    try:
        token_data = await asyncio.to_thread(
            _exchange_code_for_token,
            client_id, client_secret, _OAuthCallbackHandler.auth_code, scopes,
        )
    except Exception as exc:
        logger.error(f"Token exchange failed: {exc}")
        return None

    # Store only what's needed to refresh the token — never write client_secret.
    # The client_secret is re-read from credentials.json when needed.
    safe_token = {
        "access_token": token_data.get("access_token", ""),
        "refresh_token": token_data.get("refresh_token", ""),
        "token_type": token_data.get("token_type", "Bearer"),
        "expires_in": token_data.get("expires_in", 3600),
        "client_id": client_id,  # needed for refresh — not a secret
        "scopes": scopes,
    }

    token_path = token_output_path or str(creds_path.parent / "token.json")
    with open(token_path, "w", encoding="utf-8") as f:
        json.dump(safe_token, f, indent=2)

    # Restrict token file to current user only
    _restrict_file_to_user(token_path)

    logger.info(f"OAuth token saved to {token_path}")
    return token_path
