import asyncio
import os.path
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition

try:
    from google.auth.transport.requests import Request
    from google.oauth2.service_account import Credentials
    from google.oauth2.credentials import Credentials as OAuth2Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient import discovery
    import base64
    from email.mime.text import MIMEText
    HAS_GMAIL = True
except ImportError:
    HAS_GMAIL = False

class EmailPlugin(Plugin):
    """Gmail email integration plugin."""

    def __init__(self):
        super().__init__("email")
        self.service = None
        self.SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

    async def initialize(self) -> None:
        """Initialize Gmail service (requires credentials)."""
        if not HAS_GMAIL:
            logger.warning("Gmail dependencies not installed")
            self.enabled = False
            return

        try:
            creds_file = "credentials.json"
            token_file = "token.json"

            if os.path.exists(token_file):
                creds = OAuth2Credentials.from_authorized_user_file(token_file, self.SCOPES)
            elif os.path.exists(creds_file):
                flow = InstalledAppFlow.from_client_secrets_file(creds_file, self.SCOPES)
                creds = flow.run_local_server(port=0)
                with open(token_file, "w") as token:
                    token.write(creds.to_json())
            else:
                logger.warning("No Gmail credentials found (credentials.json)")
                self.enabled = False
                return

            self.service = await asyncio.to_thread(
                discovery.build, "gmail", "v1", credentials=creds
            )
            logger.info("Gmail service initialized")
        except Exception as e:
            logger.error(f"Gmail initialization error: {e}")
            self.enabled = False

    async def shutdown(self) -> None:
        """Cleanup on shutdown."""
        pass

    def get_tools(self) -> list[tuple[ToolDefinition, callable]]:
        """Return email tools."""
        return [
            (
                ToolDefinition(
                    name="send_email",
                    description="Send an email via Gmail",
                    parameters={
                        "type": "object",
                        "properties": {
                            "to": {"type": "string", "description": "Recipient email address"},
                            "subject": {"type": "string", "description": "Email subject"},
                            "body": {"type": "string", "description": "Email body"},
                        },
                        "required": ["to", "subject", "body"],
                    },
                ),
                self.send_email,
            ),
            (
                ToolDefinition(
                    name="list_emails",
                    description="List recent emails from inbox",
                    parameters={
                        "type": "object",
                        "properties": {
                            "limit": {"type": "integer", "description": "Number of emails to fetch", "default": 10}
                        },
                        "required": [],
                    },
                ),
                self.list_emails,
            ),
        ]

    async def send_email(self, to: str, subject: str, body: str) -> str:
        """Send an email."""
        if not self.enabled or not self.service:
            return "Gmail not configured"

        try:
            message = MIMEText(body)
            message["to"] = to
            message["subject"] = subject
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            send_message = {"raw": raw_message}

            await asyncio.to_thread(
                self.service.users().messages().send(userId="me", body=send_message).execute
            )
            return f"Email sent to {to}"
        except Exception as e:
            logger.error(f"Send email error: {e}")
            return f"Failed to send email: {str(e)}"

    async def list_emails(self, limit: int = 10) -> list[dict]:
        """List recent emails."""
        if not self.enabled or not self.service:
            return []

        try:
            results = await asyncio.to_thread(
                self.service.users()
                .messages()
                .list(userId="me", maxResults=limit)
                .execute
            )
            return [
                {
                    "id": msg["id"],
                    "snippet": msg.get("snippet", ""),
                }
                for msg in results.get("messages", [])
            ]
        except Exception as e:
            logger.error(f"List emails error: {e}")
            return []
