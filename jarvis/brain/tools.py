import ast
import asyncio
import inspect
import json
import math
import operator
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import httpx
from loguru import logger

from jarvis.models import ToolDefinition

# ── Safe expression evaluator (replaces eval) ────────────────────────────────
_SAFE_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}
_SAFE_FUNCS = {
    "abs": abs, "round": round, "min": min, "max": max, "sum": sum,
    "pow": pow, "int": int, "float": float,
    "sqrt": math.sqrt, "log": math.log, "log10": math.log10,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan, "atan2": math.atan2,
    "ceil": math.ceil, "floor": math.floor, "factorial": math.factorial,
}
_SAFE_CONSTS = {"pi": math.pi, "e": math.e, "inf": math.inf, "tau": math.tau}

def _safe_eval_node(node):
    if isinstance(node, ast.Expression):
        return _safe_eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported literal: {node.value!r}")
    if isinstance(node, ast.BinOp):
        op = _SAFE_OPS.get(type(node.op))
        if not op:
            raise ValueError(f"Operator not allowed: {type(node.op).__name__}")
        return op(_safe_eval_node(node.left), _safe_eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _SAFE_OPS.get(type(node.op))
        if not op:
            raise ValueError(f"Unary operator not allowed: {type(node.op).__name__}")
        return op(_safe_eval_node(node.operand))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only simple function calls allowed")
        func = _SAFE_FUNCS.get(node.func.id)
        if not func:
            raise ValueError(f"Function '{node.func.id}' not allowed")
        return func(*[_safe_eval_node(a) for a in node.args])
    if isinstance(node, ast.Name):
        if node.id in _SAFE_CONSTS:
            return _SAFE_CONSTS[node.id]
        raise ValueError(f"Unknown name: '{node.id}'")
    raise ValueError(f"Expression type not allowed: {type(node).__name__}")

def _math_eval(expression: str) -> str:
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _safe_eval_node(tree)
        return str(result)
    except ZeroDivisionError:
        return "Error: division by zero."
    except Exception as e:
        return f"Could not evaluate '{expression}': {e}"

# ── Shell command safety ──────────────────────────────────────────────────────
# Patterns that are always blocked regardless of policy, because they pose
# unrecoverable risk (data destruction, privilege escalation, exfiltration).
_SHELL_BLOCKLIST = re.compile(
    r"""
    (^|\s|;|&&|\|)   # command boundary
    (
      rm\s+-rf\s+/     |   # delete root
      format\s+[a-z]:  |   # format drive
      mkfs             |   # create filesystem
      dd\s+if=         |   # disk dump
      reg\s+add\s+.*run    |   # add startup registry key
      schtasks.*\/create   |   # create scheduled task
      net\s+user\s+.*\/add |   # add user account
      curl.*\|.*sh         |   # pipe remote script to shell
      wget.*\|.*sh         |   # pipe remote script to shell
      Invoke-Expression.*Download  # PowerShell remote exec
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

def _check_shell_command(command: str) -> None:
    if _SHELL_BLOCKLIST.search(command):
        raise PermissionError(
            f"Command blocked for safety: '{command[:80]}' matches a dangerous pattern. "
            "If you intended this, run it manually in a terminal."
        )

# ── File path containment ─────────────────────────────────────────────────────
_WRITE_BLOCKLIST = [
    Path(os.environ.get("APPDATA", "C:/x")) / "Microsoft/Windows/Start Menu/Programs/Startup",
    Path(os.environ.get("PROGRAMDATA", "C:/x")) / "Microsoft/Windows/Start Menu/Programs/Startup",
    Path("C:/Windows"),
    Path("C:/Program Files"),
    Path("C:/Program Files (x86)"),
    Path("C:/System32"),
]
_ALLOWED_BASE = Path.home()

def _safe_path(path: str, write: bool = False) -> Path:
    """Resolve path and enforce containment. Raises PermissionError if unsafe."""
    resolved = Path(os.path.expandvars(os.path.expanduser(path))).resolve()
    # Must be under the user's home directory
    try:
        resolved.relative_to(_ALLOWED_BASE)
    except ValueError:
        raise PermissionError(
            f"Access denied: '{resolved}' is outside your home directory. "
            f"JARVIS can only access files under {_ALLOWED_BASE}"
        )
    if write:
        for blocked in _WRITE_BLOCKLIST:
            try:
                resolved.relative_to(blocked.resolve())
                raise PermissionError(f"Writing to '{blocked}' is not allowed.")
            except ValueError:
                pass
    return resolved

def _parse_xy(val: Any) -> list[int] | None:
    """Coerce model output into [x, y] pixel integers."""
    import ast

    if val is None:
        return None
    if isinstance(val, (list, tuple)) and len(val) >= 2:
        try:
            return [int(float(val[0])), int(float(val[1]))]
        except (TypeError, ValueError):
            return None
    if isinstance(val, str):
        s = val.strip()
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, (list, tuple)) and len(parsed) >= 2:
                return [int(float(parsed[0])), int(float(parsed[1]))]
        except Exception:
            pass
        nums = [int(float(x)) for x in re.findall(r"-?\d+(?:\.\d+)?", s)]
        if len(nums) >= 2:
            return [nums[0], nums[1]]
    return None

def normalize_tool_arguments(name: str, args: Any) -> dict:
    """Fix flaky JSON from LLMs (string coords, floats-as-strings)."""
    if not isinstance(args, dict):
        return {}
    out = dict(args)
    if name == "computer":
        xy = _parse_xy(out.get("coordinate"))
        if xy is not None:
            out["coordinate"] = xy
        end = _parse_xy(out.get("end_coordinate"))
        if end is not None:
            out["end_coordinate"] = end
        if "scroll_clicks" in out:
            try:
                out["scroll_clicks"] = int(float(out["scroll_clicks"]))
            except (TypeError, ValueError):
                out["scroll_clicks"] = 3
        if "wait_ms" in out:
            try:
                out["wait_ms"] = int(float(out["wait_ms"]))
            except (TypeError, ValueError):
                out["wait_ms"] = 500
    return out

def _kwargs_for_handler(handler: Callable, args: dict) -> dict:
    sig = inspect.signature(handler)
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return args
    allowed = {
        p.name
        for p in sig.parameters.values()
        if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    return {k: v for k, v in args.items() if k in allowed}

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, tuple[ToolDefinition, Callable]] = {}

    def register(self, definition: ToolDefinition, handler: Callable) -> None:
        self._tools[definition.name] = (definition, handler)
        logger.debug(f"Registered tool: {definition.name}")

    def get_definitions(self) -> list[dict]:
        return [
            {
                "name": defn.name,
                "description": defn.description,
                "parameters": defn.parameters,
            }
            for defn, _ in self._tools.values()
        ]

    async def execute(self, name: str, args: dict) -> Any:
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' not found")
        defn, handler = self._tools[name]
        call_kwargs = _kwargs_for_handler(handler, normalize_tool_arguments(name, args))
        # Scrub sensitive fields from debug log — never log api_key values
        _safe_log = {k: ("***" if "key" in k.lower() or "secret" in k.lower() or "token" in k.lower() else v)
                     for k, v in call_kwargs.items()}
        logger.debug(f"Executing tool: {name} with args: {_safe_log}")
        try:
            if inspect.iscoroutinefunction(handler):
                result = await handler(**call_kwargs)
            else:
                result = await asyncio.to_thread(handler, **call_kwargs)
            logger.debug(f"Tool {name} result: {str(result)[:200]}")
            return result
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            raise

def create_tool_registry(
    services: dict[str, Any] | None = None,
    policy_provider: Callable[[], str] | None = None,
    approval_callback=None,
) -> ToolRegistry:
    registry = ToolRegistry()
    policy_provider = policy_provider or (lambda: "full_auto")

    if services is None:
        from jarvis.control.accessibility import AccessibilityReader
        from jarvis.control.app_launcher import AppLauncher
        from jarvis.control.browser import Browser
        from jarvis.control.clipboard import Clipboard
        from jarvis.control.keyboard import Keyboard
        from jarvis.control.mouse import Mouse
        from jarvis.control.screen import Screen
        from jarvis.control.system import SystemControl
        from jarvis.control.window import WindowControl

        services = {
            "screen":    Screen(),
            "clipboard": Clipboard(),
            "browser":   Browser(headless=False),
            "apps":      AppLauncher(),
            "keyboard":  Keyboard(),
            "mouse":     Mouse(),
            "system":    SystemControl(),
            "window":    WindowControl(),
            "accessibility": AccessibilityReader(),
        }

    if "window" not in services:
        from jarvis.control.window import WindowControl
        services["window"] = WindowControl()
    if "accessibility" not in services:
        from jarvis.control.accessibility import AccessibilityReader
        services["accessibility"] = AccessibilityReader()

    browser_started = False

    async def enforce_policy(action_name: str, risk: str) -> None:
        policy = policy_provider()
        if policy == "full_auto":
            return
        if risk == "dangerous":
            raise PermissionError(f"{action_name} requires full autonomy mode")
        if policy == "ask" and risk == "confirm":
            if approval_callback is not None:
                approved = await approval_callback(action_name, risk)
                if approved:
                    return
                raise PermissionError(f"{action_name} was declined by user.")
            raise PermissionError(
                f'{action_name} needs approval - switch Automation to '
                '"Auto-run safe actions" or "Fully autonomous" in settings.'
            )

    # System / time

    async def get_current_time() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)")

    async def get_system_info() -> dict:
        return await services["system"].get_system_info()

    async def take_screenshot(monitor: int = 1) -> str:
        return await services["screen"].take_screenshot(monitor=monitor)

    async def run_shell_command(command: str, timeout: int = 120) -> str:
        """Run a Windows shell command and return output."""
        await enforce_policy("run_shell_command", "confirm")
        _check_shell_command(command)
        timeout = max(5, min(int(timeout), 300))
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                command, shell=True, capture_output=True, text=True, timeout=timeout,
            )
            out = (result.stdout + result.stderr).strip()
            return out[:4000] if out else "(no output)"
        except subprocess.TimeoutExpired:
            return f"Command timed out after {timeout} seconds."
        except Exception as e:
            return f"Error: {e}"

    async def execute_python(code: str, timeout: int = 15) -> dict:
        """Execute Python code safely with timeout and output capture."""
        await enforce_policy("execute_python", "confirm")
        from jarvis.brain.code_executor import CodeExecutor
        executor = CodeExecutor()
        return await executor.run_python(code, timeout=timeout)

    async def execute_shell(command: str, timeout: int = 30) -> dict:
        """Execute a shell command safely with timeout and output capture."""
        await enforce_policy("execute_shell", "confirm")
        from jarvis.brain.code_executor import CodeExecutor
        executor = CodeExecutor()
        return await executor.run_shell(command, timeout=timeout)

    # Desktop audio — one-shot and live transcription

    async def transcribe_desktop_audio(duration: int = 30) -> str:
        """Capture speaker output and transcribe with Whisper. No file needed."""
        from jarvis.voice.desktop_audio import transcribe_desktop_audio as _transcribe
        return await _transcribe(duration_s=float(duration))

    async def search_chat_history(query: str) -> str:
        """Search past conversations by keyword."""
        runtime = services.get("_runtime")
        if not runtime or not runtime.memory:
            return "Chat history not available."
        results = await runtime.memory.search_sessions(query, limit=8)
        if not results:
            return f"No conversations found containing '{query}'."
        lines = [f"Found {len(results)} session(s) matching '{query}':\n"]
        for r in results:
            ts = (r.get("updated_at") or "")[:16]
            title = r.get("title") or "(untitled)"
            snippet = (r.get("snippet") or "")[:120]
            lines.append(f"• [{ts}] {title}\n  …{snippet}…\n  session_id: {r['session_id']}")
        return "\n".join(lines)

    async def get_chat_session(session_id: str) -> str:
        """Retrieve the full content of a past chat session."""
        runtime = services.get("_runtime")
        if not runtime or not runtime.memory:
            return "Chat history not available."
        msgs = await runtime.memory.get_session_messages(session_id)
        if not msgs:
            return f"Session '{session_id}' not found or is empty."
        lines = []
        for m in msgs[-40:]:  # last 40 messages to stay within limits
            role = "You" if m["role"] == "user" else "JARVIS"
            ts = (m.get("timestamp") or "")[:16]
            lines.append(f"[{ts}] {role}: {m['content'][:500]}")
        return "\n".join(lines)

    async def start_live_transcription() -> str:
        """Start live subtitle overlay and save session to file."""
        svc = getattr(services.get("_runtime"), "_live_transcription", None)
        if svc is None:
            return "Live transcription service not available."
        return await svc.start()

    async def stop_live_transcription() -> str:
        """Stop live transcription and subtitle overlay."""
        svc = getattr(services.get("_runtime"), "_live_transcription", None)
        if svc is None:
            return "Live transcription service not available."
        return await svc.stop()

    async def get_recent_transcript(seconds: int = 120) -> str:
        """Get the last N seconds of live transcription for Q&A."""
        svc = getattr(services.get("_runtime"), "_live_transcription", None)
        if svc is None:
            return "Live transcription is not running."
        return svc.get_recent_transcript(seconds=float(seconds))

    async def recall_transcription(session_id: str = "") -> str:
        """Read a saved transcription file. Leave session_id blank to list available sessions."""
        from jarvis.voice.live_transcription import (
            list_transcription_sessions,
            read_transcription_session,
        )
        if not session_id:
            sessions = list_transcription_sessions()
            if not sessions:
                return "No saved transcriptions found."
            return "Available sessions:\n" + "\n".join(f"  {s}" for s in sessions[-20:])
        return read_transcription_session(session_id)

    # Clipboard

    async def read_clipboard() -> str:
        return await services["clipboard"].read()

    async def write_clipboard(text: str) -> str:
        await enforce_policy("write_clipboard", "safe")
        await services["clipboard"].write(text)
        return "Clipboard updated."

    # Browser

    async def _ensure_browser():
        nonlocal browser_started
        if not browser_started:
            await services["browser"].initialize()
            browser_started = True

    async def browser_navigate(url: str) -> str:
        await enforce_policy("browser_navigate", "safe")
        await _ensure_browser()
        return await services["browser"].navigate(url)

    async def browser_get_content() -> str:
        await _ensure_browser()
        content = await services["browser"].get_content()
        return str(content)[:3000] if content else "(empty page)"

    async def browser_click(selector: str | None = None, text: str | None = None, nth: int = 0) -> str:
        await enforce_policy("browser_click", "safe")
        await _ensure_browser()
        return await services["browser"].click(selector=selector, text=text, nth=int(nth))

    async def browser_type(
        selector: str | None = None,
        text: str = "",
        submit: bool = False,
        clear_first: bool = True,
    ) -> str:
        await enforce_policy("browser_type", "safe")
        await _ensure_browser()
        return await services["browser"].fill(
            selector=selector,
            text=text,
            submit=bool(submit),
            clear_first=bool(clear_first),
        )

    async def browser_press_key(key: str) -> str:
        await enforce_policy("browser_press_key", "safe")
        await _ensure_browser()
        return await services["browser"].press_key(key)

    async def browser_scroll(direction: str = "down", amount: int = 600) -> str:
        await enforce_policy("browser_scroll", "safe")
        await _ensure_browser()
        return await services["browser"].scroll(direction=direction, amount=int(amount))

    async def browser_wait_for(
        text: str | None = None,
        selector: str | None = None,
        timeout_ms: int = 5000,
    ) -> str:
        await _ensure_browser()
        return await services["browser"].wait_for(text=text, selector=selector, timeout_ms=int(timeout_ms))

    async def browser_tabs() -> list[dict]:
        await _ensure_browser()
        return await services["browser"].list_tabs()

    async def browser_close_tab(index: int = -1) -> str:
        await enforce_policy("browser_close_tab", "safe")
        await _ensure_browser()
        return await services["browser"].close_tab(index=int(index))

    # Web search (DuckDuckGo HTML scrape)

    async def search_web(query: str) -> str:
        """Search the web and return top results with titles and snippets."""
        try:
            url = "https://html.duckduckgo.com/html/"
            async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
                r = await client.post(
                    url,
                    data={"q": query},
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JARVIS/1.0"},
                )
            # Parse result snippets from HTML
            text = r.text
            results: list[str] = []
            # Extract result blocks: <a class="result__a" ...>title</a> + <a class="result__snippet">snippet</a>
            title_matches = re.findall(r'class="result__a"[^>]*>([^<]+)</a>', text)
            snippet_matches = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', text, re.DOTALL)
            for i, title in enumerate(title_matches[:8]):
                title_clean = re.sub(r'<[^>]+>', '', title).strip()
                snippet = ""
                if i < len(snippet_matches):
                    snippet = re.sub(r'<[^>]+>', '', snippet_matches[i]).strip()
                    snippet = re.sub(r'\s+', ' ', snippet)
                if title_clean:
                    entry = f"{i+1}. {title_clean}"
                    if snippet:
                        entry += f"\n   {snippet[:200]}"
                    results.append(entry)

            if results:
                return "\n\n".join(results)

            # Fallback: DDG instant answers API
            api_url = "https://api.duckduckgo.com/"
            params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(api_url, params=params)
            data = r.json()
            parts: list[str] = []
            if data.get("AbstractText"):
                parts.append(data["AbstractText"])
            for item in data.get("RelatedTopics", [])[:5]:
                if isinstance(item, dict) and item.get("Text"):
                    parts.append(item["Text"])
            if parts:
                return "\n\n".join(parts)[:2000]

            # Last resort: open in browser
            await browser_navigate(f"https://duckduckgo.com/?q={query.replace(' ', '+')}")
            return f"Opened DuckDuckGo search for: {query}"
        except Exception as e:
            return f"Search failed: {e}"

    # Weather

    async def get_weather(city: str = "") -> str:
        """Get current weather using wttr.in."""
        try:
            loc = city.strip() or ""
            url = f"https://wttr.in/{loc}?format=j1"
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(url, headers={"User-Agent": "JARVIS/1.0"})
            data = r.json()
            current = data["current_condition"][0]
            area = data["nearest_area"][0]
            city_name = area["areaName"][0]["value"]
            country   = area["country"][0]["value"]
            desc    = current["weatherDesc"][0]["value"]
            temp_c  = current["temp_C"]
            feels_c = current["FeelsLikeC"]
            humidity = current["humidity"]
            wind    = current["windspeedKmph"]
            return (
                f"Weather in {city_name}, {country}: {desc}. "
                f"Temperature: {temp_c}°C (feels like {feels_c}°C). "
                f"Humidity: {humidity}%. Wind: {wind} km/h."
            )
        except Exception as e:
            return f"Could not fetch weather: {e}"

    # Calculator

    async def calculate(expression: str) -> str:
        """Evaluate a mathematical expression safely (AST-based, no eval)."""
        return _math_eval(expression)

    # File operations

    async def read_file(path: str) -> str:
        """Read a text file from disk (max 4000 chars, home directory only)."""
        await enforce_policy("read_file", "safe")
        try:
            safe = _safe_path(path, write=False)
            with open(safe, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(4000)
            return content or "(empty file)"
        except PermissionError as e:
            return f"Access denied: {e}"
        except FileNotFoundError:
            return f"File not found: {path}"
        except Exception as e:
            return f"Could not read file: {e}"

    async def write_file(path: str, content: str) -> str:
        """Write text to a file on disk (home directory only, startup paths blocked)."""
        await enforce_policy("write_file", "confirm")
        try:
            safe = _safe_path(path, write=True)
            safe.parent.mkdir(parents=True, exist_ok=True)
            with open(safe, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Written to {safe}"
        except PermissionError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Could not write file: {e}"

    async def list_directory(path: str = ".") -> str:
        """List files in a directory (home directory only)."""
        await enforce_policy("list_directory", "safe")
        try:
            safe = _safe_path(path, write=False)
            entries = sorted(os.listdir(safe))
            return "\n".join(entries[:100]) or "(empty)"
        except PermissionError as e:
            return f"Access denied: {e}"
        except Exception as e:
            return f"Could not list directory: {e}"

    # Apps / UI

    async def launch_app(app_name: str) -> str:
        await enforce_policy("launch_app", "confirm")
        if app_name.lower().strip() in ("jarvis", "jarvis.exe"):
            return "Cannot launch myself — I'm already running."
        return await services["apps"].launch(app_name)

    async def close_app(app_name: str) -> str:
        await enforce_policy("close_app", "confirm")
        closed = await services["apps"].close(app_name)
        return f"Closed {app_name}" if closed else f"Could not close {app_name}"

    # Window management

    async def find_window(title: str = "") -> str:
        """List visible windows, optionally filtered by title substring."""
        windows = await services["window"].list_windows()
        if title:
            title_lower = title.lower()
            windows = [w for w in windows if title_lower in w.get("title", "").lower()]
        if not windows:
            return "No windows found" + (f" matching '{title}'" if title else "")
        lines = [f"• {w['title']} ({w['width']}x{w['height']})" for w in windows[:15]]
        return "\n".join(lines)

    async def focus_window(title: str) -> str:
        """Bring a window to the foreground by title (fuzzy match)."""
        await enforce_policy("focus_window", "safe")
        ok = await services["window"].focus_window(title)
        if ok:
            return f"Focused: {title}"
        return f"No window found matching '{title}'"

    async def get_active_window() -> str:
        """Get the title of the currently active window."""
        return await services["window"].get_active_window()

    # Computer (unified desktop control)

    async def computer(
        action: str,
        coordinate: list[int] | None = None,
        text: str | None = None,
        key: str | None = None,
        end_coordinate: list[int] | None = None,
        scroll_clicks: int = 3,
        scroll_direction: str = "down",
        wait_ms: int = 500,
        window_title: str | None = None,
    ) -> str:
        """Desktop automation: mouse, keyboard, scroll, drag, waits, screenshots."""
        await enforce_policy("computer", "confirm")

        if action == "wait":
            delay = max(0, min(int(wait_ms), 30_000))
            await asyncio.sleep(delay / 1000.0)
            return f"Waited {delay} ms."

        if action == "screenshot":
            # Return the raw path so app.py can detect it reliably and embed
            # the image for vision-capable providers (Claude).
            return await take_screenshot()

        if action == "scroll":
            if not coordinate:
                return "Error: coordinate required for scroll."
            x, y = int(coordinate[0]), int(coordinate[1])
            if window_title:
                await services["window"].focus_window(window_title)
            await services["mouse"].move(x, y, duration=0.12)
            remaining = max(1, int(scroll_clicks))
            while remaining > 0:
                step = min(3, remaining)
                await services["mouse"].scroll(x, y, step, scroll_direction)
                remaining -= step
                if remaining > 0:
                    await asyncio.sleep(0.15)
            path = await take_screenshot()
            return f"Scrolled {scroll_direction} {scroll_clicks} step(s) at ({x}, {y}). Screenshot: {path}"

        if action == "drag":
            if not coordinate or not end_coordinate:
                return "Error: coordinate and end_coordinate required for drag."
            x1, y1 = int(coordinate[0]), int(coordinate[1])
            x2, y2 = int(end_coordinate[0]), int(end_coordinate[1])
            if window_title:
                await services["window"].focus_window(window_title)
            await services["mouse"].move(x1, y1, duration=0.12)
            await services["mouse"].drag(x1, y1, x2, y2, duration=0.4, button="left")
            path = await take_screenshot()
            return f"Dragged from ({x1}, {y1}) to ({x2}, {y2}). Screenshot: {path}"

        if action in ("mouse_move", "left_click", "right_click", "middle_click", "double_click", "triple_click"):
            if not coordinate:
                return "Error: coordinate required for mouse actions."
            x, y = int(coordinate[0]), int(coordinate[1])
            if window_title:
                await services["window"].focus_window(window_title)
            if action == "mouse_move":
                await services["mouse"].move(x, y, duration=0.18)
                return f"Moved mouse to ({x}, {y})."
            if action == "double_click":
                await services["mouse"].double_click(x, y, button="left")
                # Auto-screenshot after click for visual feedback
                await asyncio.sleep(0.4)
                path = await take_screenshot()
                return f"Double-clicked at ({x}, {y}). Screenshot: {path}"
            if action == "triple_click":
                await services["mouse"].triple_click(x, y)
                await asyncio.sleep(0.3)
                path = await take_screenshot()
                return f"Triple-clicked at ({x}, {y}). Screenshot: {path}"
            button = action.replace("_click", "")
            await services["mouse"].move(x, y, duration=0.08)
            await services["mouse"].click(x, y, button=button)
            # Auto-screenshot after click for visual feedback
            await asyncio.sleep(0.4)
            path = await take_screenshot()
            return f"Clicked {button} at ({x}, {y}). Screenshot: {path}"

        if action == "type":
            if not text:
                return "Error: text required for type action."
            if window_title:
                await services["window"].focus_window(window_title)
            await services["keyboard"].type_text(text)
            await asyncio.sleep(0.2)
            path = await take_screenshot()
            return f"Typed text. Screenshot: {path}"

        if action == "key":
            if not key:
                return "Error: key required for key action."
            if window_title:
                await services["window"].focus_window(window_title)
            await services["keyboard"].press_key(key)
            await asyncio.sleep(0.3)
            path = await take_screenshot()
            return f"Pressed key: {key}. Screenshot: {path}"

        return f"Unknown computer action: {action}"

    async def browser_get_structured_content() -> str:
        await _ensure_browser()
        return await services["browser"].get_structured_content()

    async def browser_find_elements(query: str, max_results: int = 10) -> list[dict]:
        await _ensure_browser()
        return await services["browser"].find_elements(query, max_results=int(max_results))

    async def browser_screenshot(full_page: bool = False) -> str:
        await _ensure_browser()
        return await services["browser"].screenshot(full_page=bool(full_page))

    async def read_window_elements(title: str = "", max_elements: int = 50) -> list[dict]:
        return await services["accessibility"].get_window_elements(
            title=title, max_elements=int(max_elements)
        )

    async def find_ui_element(name: str, title: str = "") -> dict | str:
        result = await services["accessibility"].find_element(name=name, title=title)
        if result is None:
            return f"No UI element found matching '{name}'"
        return result

    async def set_volume(level: int) -> str:
        await enforce_policy("set_volume", "safe")
        await services["system"].set_volume(level)
        return f"Volume set to {level}%"

    async def describe_screen() -> str:
        """Get a visual description of the current screen state using the local vision model.
        Returns what is visually present: active application, content, and UI elements."""
        parts: list[str] = []

        # PRIMARY: Moondream local vision — actual visual understanding
        try:
            import asyncio as _asyncio
            from jarvis.brain.local_vision import get_local_vision
            lv = get_local_vision()
            if lv.ready:
                desc = await _asyncio.to_thread(
                    lv.describe_screen,
                    "Describe what you see on this screen: the active application, "
                    "main visible content, any text, UI controls, and what the user appears to be doing."
                )
                if desc and len(desc) > 20:
                    parts.append(f"[Visual description]: {desc}")
        except Exception:
            pass

        # SUPPLEMENT: Active window title via win32
        try:
            import ctypes as _ct
            hwnd = _ct.windll.user32.GetForegroundWindow()
            if hwnd:
                buf = _ct.create_unicode_buffer(512)
                _ct.windll.user32.GetWindowTextW(hwnd, buf, 512)
                title = buf.value.strip()
                from ctypes import wintypes as _wt
                rect = _wt.RECT()
                _ct.windll.user32.GetWindowRect(hwnd, _ct.byref(rect))
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                if title:
                    parts.append(f"Active window: {title} ({w}x{h} at {rect.left},{rect.top})")
        except Exception:
            pass

        # FALLBACK: Accessibility elements if Moondream not available
        if len(parts) <= 1:
            try:
                acc = services.get("accessibility")
                if acc:
                    elements = await acc.get_window_elements(title="", max_elements=30)
                    el_lines = []
                    for el in elements:
                        if "error" in el:
                            continue
                        name = el.get("name", "").strip()
                        ctrl_type = el.get("type", el.get("role", "")).strip()
                        bounds = el.get("bounds", el.get("rect", {}))
                        if not name or not ctrl_type:
                            continue
                        coord = ""
                        if bounds:
                            cx = bounds.get("x", 0) + bounds.get("w", bounds.get("width", 0)) // 2
                            cy = bounds.get("y", 0) + bounds.get("h", bounds.get("height", 0)) // 2
                            coord = f" at ({cx},{cy})"
                        enabled = "" if el.get("enabled", True) else " [disabled]"
                        el_lines.append(f"  [{ctrl_type}] {name}{coord}{enabled}")
                    if el_lines:
                        parts.append("UI elements:\n" + "\n".join(el_lines))
            except Exception:
                pass

        return "\n".join(parts) if parts else "No screen elements readable (no active window found)."

    async def describe_screen_text() -> str:
        """Get a text description of the current screen state for non-vision AI.
        Includes active window, mouse position, and visible UI elements with names and coordinates."""
        acc = services.get("accessibility")
        if not acc:
            return "Accessibility service not available."
        return await acc.get_screen_text_description(max_elements=40)

    async def get_focused_app() -> dict:
        """Get the title and app of the currently focused window (rich dict from accessibility API)."""
        acc = services.get("accessibility")
        if not acc:
            return {"error": "Accessibility service not available."}
        return await acc.get_active_app()

    async def click_element(name: str, window_title: str = "") -> str:
        """Click a UI element by its accessibility name (for non-vision providers)."""
        await enforce_policy("click_element", "confirm")
        acc = services.get("accessibility")
        if not acc:
            return "Accessibility service not available."
        return await acc.click_by_name(name, title=window_title)

    # Workflow tools

    _workflow_engine = None

    async def _get_workflow_engine():
        nonlocal _workflow_engine
        if _workflow_engine is None:
            from jarvis.brain.workflow_engine import WorkflowEngine
            _workflow_engine = WorkflowEngine()
        return _workflow_engine

    async def create_workflow(name: str, steps: str, description: str = "") -> str:
        """Create a multi-step workflow. steps is JSON array: [{"name":"...", "instruction":"..."}]"""
        engine = await _get_workflow_engine()
        try:
            steps_list = json.loads(steps)
        except json.JSONDecodeError:
            return "Error: steps must be a JSON array"
        wf = await engine.create_workflow(name, steps_list, description)
        return f"Workflow '{name}' created with ID: {wf.id} ({len(steps_list)} steps)"

    async def list_workflows() -> str:
        """List all saved workflows."""
        engine = await _get_workflow_engine()
        workflows = engine.list_workflows()
        if not workflows:
            return "No workflows saved."
        lines = []
        for wf in workflows:
            lines.append(f"- {wf['id']}: {wf['name']} [{wf['status']}] ({wf['step_count']} steps)")
        return "\n".join(lines)

    async def get_workflow_details(workflow_id: str) -> str:
        """Get detailed information about a workflow."""
        engine = await _get_workflow_engine()
        wf = engine.get_workflow(workflow_id)
        if not wf:
            return f"Workflow '{workflow_id}' not found"
        lines = [
            f"Workflow: {wf.name}",
            f"ID: {wf.id}",
            f"Status: {wf.status.value}",
            f"Description: {wf.description}",
            f"Steps: {len(wf.steps)}",
        ]
        for step in wf.steps:
            lines.append(f"  - {step.name} ({step.status.value})")
            if step.result:
                lines.append(f"    Result: {step.result[:100]}...")
            if step.error:
                lines.append(f"    Error: {step.error}")
        return "\n".join(lines)

    async def run_workflow_step(workflow_id: str, step_id: str) -> str:
        """Run a single step of an existing workflow by step ID and return its result."""
        engine = await _get_workflow_engine()
        wf = engine.get_workflow(workflow_id)
        if not wf:
            return f"Workflow '{workflow_id}' not found"

        step = next((s for s in wf.steps if s.id == step_id), None)
        if not step:
            return f"Step '{step_id}' not found in workflow '{workflow_id}'"

        # Ensure workflow is in active registry so save_checkpoint works
        engine._active_workflows[workflow_id] = wf

        from jarvis.brain.workflow_engine import StepStatus
        import time as _time

        step.status = StepStatus.RUNNING
        step.started_at = _time.time()
        wf.save_checkpoint()

        # We need an ai_executor; since tools.py doesn't have direct AI access,
        # we mark the step as requiring external execution and return its instruction.
        # The caller should use execute_workflow for full AI-driven execution.
        # Here we return the step instruction so the caller can act on it.
        step.status = StepStatus.PENDING
        step.started_at = 0.0
        wf.save_checkpoint()

        return (
            f"Step '{step.name}' (ID: {step_id}) in workflow '{wf.name}':\n"
            f"Status: {step.status.value}\n"
            f"Instruction: {step.instruction}\n"
            f"Hint: Use execute_workflow to run steps with AI execution, "
            f"or call this tool to inspect step details."
        )

    # Tool registration

    tools_to_register = [
        (
            ToolDefinition(
                name="computer",
                description=(
                    "Windows desktop: screenshot/wait/move/click/double/triple/scroll/drag/type/key. "
                    "Returns auto-screenshot after clicks/type/key. Integer px from DISPLAY primary. "
                    "If you cannot see the screenshot image, call describe_screen or "
                    "read_window_elements FIRST to discover clickable targets and their coordinates."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "screenshot",
                                "wait",
                                "mouse_move",
                                "left_click",
                                "right_click",
                                "middle_click",
                                "double_click",
                                "triple_click",
                                "scroll",
                                "drag",
                                "key",
                                "type",
                            ],
                        },
                        "coordinate": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "minItems": 2,
                            "maxItems": 2,
                            "description": "[x, y] screen pixels",
                        },
                        "end_coordinate": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "minItems": 2,
                            "maxItems": 2,
                            "description": "drag end [x, y]",
                        },
                        "text": {"type": "string", "description": "For type action"},
                        "key": {"type": "string", "description": "For key action — e.g. enter, ctrl+s, alt+tab"},
                        "scroll_clicks": {"type": "integer", "default": 3},
                        "scroll_direction": {
                            "type": "string",
                            "enum": ["up", "down", "left", "right"],
                            "default": "down",
                        },
                        "wait_ms": {"type": "integer", "default": 500},
                        "window_title": {"type": "string", "description": "Focus this window before acting"},
                    },
                    "required": ["action"],
                },
            ),
            computer,
        ),
        (
            ToolDefinition(
                name="get_current_time",
                description="Get the current date, time, and day of the week",
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            get_current_time,
        ),
        (
            ToolDefinition(
                name="get_system_info",
                description="Get current CPU, memory, and disk usage statistics",
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            get_system_info,
        ),
        (
            ToolDefinition(
                name="take_screenshot",
                description="Capture a screenshot of the screen",
                parameters={
                    "type": "object",
                    "properties": {"monitor": {"type": "integer", "description": "Monitor number (default 1)"}},
                    "required": [],
                },
            ),
            take_screenshot,
        ),
        (
            ToolDefinition(
                name="run_shell_command",
                description="Run a Windows shell command (cmd/PowerShell) and return the output",
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The shell command to run"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds (default 120, max 300)"},
                    },
                    "required": ["command"],
                },
            ),
            run_shell_command,
        ),
        (
            ToolDefinition(
                name="search_web",
                description="Search the web and return top results with titles and snippets",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "Search query"}},
                    "required": ["query"],
                },
            ),
            search_web,
        ),
        (
            ToolDefinition(
                name="get_weather",
                description="Get current weather for a city (blank for auto-location)",
                parameters={
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": [],
                },
            ),
            get_weather,
        ),
        (
            ToolDefinition(
                name="calculate",
                description="Evaluate a math expression (sqrt, sin, cos, log, pi, e, etc.)",
                parameters={
                    "type": "object",
                    "properties": {"expression": {"type": "string", "description": "e.g. '2**10 + sqrt(16)'"}},
                    "required": ["expression"],
                },
            ),
            calculate,
        ),
        (
            ToolDefinition(
                name="read_clipboard",
                description="Read the current text from the clipboard",
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            read_clipboard,
        ),
        (
            ToolDefinition(
                name="write_clipboard",
                description="Write text to the clipboard",
                parameters={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            ),
            write_clipboard,
        ),
        (
            ToolDefinition(
                name="read_file",
                description="Read a text file from disk",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "File path (supports ~ for home)"}},
                    "required": ["path"],
                },
            ),
            read_file,
        ),
        (
            ToolDefinition(
                name="write_file",
                description="Write text to a file on disk",
                parameters={
                    "type": "object",
                    "properties": {
                        "path":    {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            ),
            write_file,
        ),
        (
            ToolDefinition(
                name="list_directory",
                description="List files and folders in a directory",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "Directory path (default: current)"}},
                    "required": [],
                },
            ),
            list_directory,
        ),
        (
            ToolDefinition(
                name="browser_navigate",
                description="Open a URL in the desktop browser",
                parameters={
                    "type": "object",
                    "properties": {"url": {"type": "string", "description": "Full URL to navigate to"}},
                    "required": ["url"],
                },
            ),
            browser_navigate,
        ),
        (
            ToolDefinition(
                name="browser_get_content",
                description="Get the text content of the current browser page",
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            browser_get_content,
        ),
        (
            ToolDefinition(
                name="browser_click",
                description="Click a browser element by CSS selector or visible text in the managed browser session",
                parameters={
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string"},
                        "text": {"type": "string"},
                        "nth": {"type": "integer", "default": 0},
                    },
                    "required": [],
                },
            ),
            browser_click,
        ),
        (
            ToolDefinition(
                name="browser_type",
                description="Type into a browser field by CSS selector in the managed browser session",
                parameters={
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string"},
                        "text": {"type": "string"},
                        "submit": {"type": "boolean", "default": False},
                        "clear_first": {"type": "boolean", "default": True},
                    },
                    "required": ["text"],
                },
            ),
            browser_type,
        ),
        (
            ToolDefinition(
                name="browser_press_key",
                description="Press a key in the managed browser session",
                parameters={
                    "type": "object",
                    "properties": {"key": {"type": "string"}},
                    "required": ["key"],
                },
            ),
            browser_press_key,
        ),
        (
            ToolDefinition(
                name="browser_scroll",
                description="Scroll inside the managed browser session",
                parameters={
                    "type": "object",
                    "properties": {
                        "direction": {"type": "string", "enum": ["up", "down", "left", "right"], "default": "down"},
                        "amount": {"type": "integer", "default": 600},
                    },
                    "required": [],
                },
            ),
            browser_scroll,
        ),
        (
            ToolDefinition(
                name="browser_wait_for",
                description="Wait for text or a selector to appear in the managed browser session",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "selector": {"type": "string"},
                        "timeout_ms": {"type": "integer", "default": 5000},
                    },
                    "required": [],
                },
            ),
            browser_wait_for,
        ),
        (
            ToolDefinition(
                name="browser_tabs",
                description="List open tabs in the managed browser session",
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            browser_tabs,
        ),
        (
            ToolDefinition(
                name="browser_close_tab",
                description="Close a tab in the managed browser session by index",
                parameters={
                    "type": "object",
                    "properties": {"index": {"type": "integer", "default": -1}},
                    "required": [],
                },
            ),
            browser_close_tab,
        ),
        (
            ToolDefinition(
                name="launch_app",
                description="Launch an application on the computer by name",
                parameters={
                    "type": "object",
                    "properties": {"app_name": {"type": "string"}},
                    "required": ["app_name"],
                },
            ),
            launch_app,
        ),
        (
            ToolDefinition(
                name="close_app",
                description="Close a running application by name",
                parameters={
                    "type": "object",
                    "properties": {"app_name": {"type": "string"}},
                    "required": ["app_name"],
                },
            ),
            close_app,
        ),
        (
            ToolDefinition(
                name="find_window",
                description="List visible windows, optionally filtered by title substring",
                parameters={
                    "type": "object",
                    "properties": {"title": {"type": "string", "description": "Filter by title (optional)"}},
                    "required": [],
                },
            ),
            find_window,
        ),
        (
            ToolDefinition(
                name="focus_window",
                description="Bring a window to the foreground by title (fuzzy match)",
                parameters={
                    "type": "object",
                    "properties": {"title": {"type": "string"}},
                    "required": ["title"],
                },
            ),
            focus_window,
        ),
        (
            ToolDefinition(
                name="get_active_window",
                description="Get the title of the currently active/focused window",
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            get_active_window,
        ),
        (
            ToolDefinition(
                name="set_volume",
                description="Set the system audio volume (0-100)",
                parameters={
                    "type": "object",
                    "properties": {"level": {"type": "integer", "description": "Volume 0–100"}},
                    "required": ["level"],
                },
            ),
            set_volume,
        ),
        (
            ToolDefinition(
                name="browser_get_structured_content",
                description="Get structured page content: title, URL, headings, links, form fields, buttons, and main text",
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            browser_get_structured_content,
        ),
        (
            ToolDefinition(
                name="browser_find_elements",
                description="Find interactive elements on the page by name/text (searches ARIA labels, visible text, placeholders, titles)",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Text to search for in element names/labels"},
                        "max_results": {"type": "integer", "default": 10},
                    },
                    "required": ["query"],
                },
            ),
            browser_find_elements,
        ),
        (
            ToolDefinition(
                name="browser_screenshot",
                description="Take a screenshot of just the browser page (not the full desktop)",
                parameters={
                    "type": "object",
                    "properties": {
                        "full_page": {"type": "boolean", "default": False, "description": "Capture full scrollable page"},
                    },
                    "required": [],
                },
            ),
            browser_screenshot,
        ),
        (
            ToolDefinition(
                name="read_window_elements",
                description="Read the accessibility tree of a desktop window — lists buttons, fields, labels, and their positions",
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Window title to read (blank = active window)"},
                        "max_elements": {"type": "integer", "default": 50},
                    },
                    "required": [],
                },
            ),
            read_window_elements,
        ),
        (
            ToolDefinition(
                name="find_ui_element",
                description="Find a specific UI element by name in a desktop window — returns its position and type",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Element name/label to find"},
                        "title": {"type": "string", "description": "Window title to search (blank = active window)"},
                    },
                    "required": ["name"],
                },
            ),
            find_ui_element,
        ),
        (
            ToolDefinition(
                name="describe_screen",
                description=(
                    "Get a text-only description of the current screen: active window title, "
                    "visible UI elements (buttons, labels, fields) with their roles and pixel coordinates. "
                    "Use this instead of screenshots when you cannot see images."
                ),
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            describe_screen,
        ),
        (
            ToolDefinition(
                name="describe_screen_text",
                description=(
                    "Get a text description of the current screen state for non-vision AI providers. "
                    "Lists the active window, mouse position, and visible UI elements with names and coordinates. "
                    "Use this when the provider cannot process images (e.g., Mistral non-pixtral, Groq non-vision)."
                ),
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            describe_screen_text,
        ),
        (
            ToolDefinition(
                name="get_focused_app",
                description="Get the title and app name of the currently focused window (returns dict with title, app, pid)",
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            get_focused_app,
        ),
        (
            ToolDefinition(
                name="click_element",
                description=(
                    "Click a UI element by its accessibility name. "
                    "Use describe_screen_text first to discover element names. "
                    "More reliable than pixel coordinates for non-vision providers."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Element name/label to click"},
                        "window_title": {"type": "string", "description": "Window title to search (blank = active window)"},
                    },
                    "required": ["name"],
                },
            ),
            click_element,
        ),
        (
            ToolDefinition(
                name="create_workflow",
                description="Create a multi-step workflow that can be executed and resumed. Steps are JSON with name, instruction, and optional depends_on fields.",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Workflow name"},
                        "steps": {"type": "string", "description": "JSON array of steps: [{\"name\":\"...\", \"instruction\":\"...\", \"depends_on\":[...]}]"},
                        "description": {"type": "string", "description": "Workflow description (optional)"},
                    },
                    "required": ["name", "steps"],
                },
            ),
            create_workflow,
        ),
        (
            ToolDefinition(
                name="list_workflows",
                description="List all saved workflows with their status",
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            list_workflows,
        ),
        (
            ToolDefinition(
                name="get_workflow_details",
                description="Get detailed information about a specific workflow",
                parameters={
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string", "description": "Workflow ID to retrieve"},
                    },
                    "required": ["workflow_id"],
                },
            ),
            get_workflow_details,
        ),
        (
            ToolDefinition(
                name="run_workflow_step",
                description=(
                    "Inspect or run a single step of an existing workflow by step ID. "
                    "Returns the step's instruction and current status. "
                    "Use create_workflow + execute_workflow for full AI-driven execution."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "workflow_id": {"type": "string", "description": "Workflow ID containing the step"},
                        "step_id": {"type": "string", "description": "Step ID to run (e.g. 'step_0', 'step_1')"},
                    },
                    "required": ["workflow_id", "step_id"],
                },
            ),
            run_workflow_step,
        ),
        (
            ToolDefinition(
                name="execute_python",
                description="Execute Python code safely in a sandboxed subprocess with timeout and output capture",
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Python code to execute"},
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds (default 15, max 15)",
                        },
                    },
                    "required": ["code"],
                },
            ),
            execute_python,
        ),
        (
            ToolDefinition(
                name="execute_shell",
                description="Execute a shell command safely in a subprocess with timeout and output capture",
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command to execute"},
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds (default 30, max 120)",
                        },
                    },
                    "required": ["command"],
                },
            ),
            execute_shell,
        ),
        (
            ToolDefinition(
                name="search_chat_history",
                description="Search past conversations by keyword. Returns matching session IDs and snippets.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Keyword or phrase to search for"},
                    },
                    "required": ["query"],
                },
            ),
            search_chat_history,
        ),
        (
            ToolDefinition(
                name="get_chat_session",
                description="Retrieve the full message content of a specific past conversation by session_id.",
                parameters={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Session ID from search_chat_history"},
                    },
                    "required": ["session_id"],
                },
            ),
            get_chat_session,
        ),
        (
            ToolDefinition(
                name="start_live_transcription",
                description=(
                    "Start live subtitle overlay — captures speaker output continuously, "
                    "shows captions on screen in real time, and saves the session to a file. "
                    "Use this for calls, videos, lectures, or any ongoing audio."
                ),
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            start_live_transcription,
        ),
        (
            ToolDefinition(
                name="stop_live_transcription",
                description="Stop the live subtitle overlay and close the transcription session.",
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            stop_live_transcription,
        ),
        (
            ToolDefinition(
                name="get_recent_transcript",
                description=(
                    "Get the last N seconds of live transcription text so you can answer "
                    "questions about what was just said. Requires live transcription to be running."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "seconds": {
                            "type": "integer",
                            "description": "How many seconds back to retrieve (default 120)",
                        },
                    },
                    "required": [],
                },
            ),
            get_recent_transcript,
        ),
        (
            ToolDefinition(
                name="recall_transcription",
                description=(
                    "Read a saved transcription session from a previous recording. "
                    "Leave session_id blank to list all available sessions."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID like '2026-06-02_22-30' — leave blank to list all",
                        },
                    },
                    "required": [],
                },
            ),
            recall_transcription,
        ),
        (
            ToolDefinition(
                name="transcribe_desktop_audio",
                description=(
                    "Listen to whatever is currently playing through the speakers "
                    "(video, music, call, livestream) and return a transcription. "
                    "Works on any app — YouTube, Spotify, Zoom, anything. "
                    "No file or link needed. Specify how many seconds to listen."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "duration": {
                            "type": "integer",
                            "description": "How many seconds of audio to capture (default 30, max 300)",
                        },
                    },
                    "required": [],
                },
            ),
            transcribe_desktop_audio,
        ),
    ]

    for defn, handler in tools_to_register:
        registry.register(defn, handler)

    return registry
