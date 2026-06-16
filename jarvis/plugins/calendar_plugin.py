import asyncio
import os.path
from datetime import datetime, timedelta
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition

try:
    from google.oauth2.credentials import Credentials as OAuth2Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient import discovery
    HAS_CALENDAR = True
except ImportError:
    HAS_CALENDAR = False

class CalendarPlugin(Plugin):
    """Google Calendar integration plugin."""

    def __init__(self):
        super().__init__("calendar")
        self.service = None
        self.SCOPES = ["https://www.googleapis.com/auth/calendar"]

    async def initialize(self) -> None:
        """Initialize Google Calendar service."""
        if not HAS_CALENDAR:
            logger.warning("Google Calendar dependencies not installed")
            self.enabled = False
            return

        try:
            creds_file = "credentials.json"
            token_file = "calendar_token.json"

            if os.path.exists(token_file):
                creds = OAuth2Credentials.from_authorized_user_file(token_file, self.SCOPES)
            elif os.path.exists(creds_file):
                flow = InstalledAppFlow.from_client_secrets_file(creds_file, self.SCOPES)
                creds = flow.run_local_server(port=0)
                with open(token_file, "w") as token:
                    token.write(creds.to_json())
            else:
                logger.warning("No Google Calendar credentials found")
                self.enabled = False
                return

            self.service = await asyncio.to_thread(
                discovery.build, "calendar", "v3", credentials=creds
            )
            logger.info("Google Calendar service initialized")
        except Exception as e:
            logger.error(f"Calendar initialization error: {e}")
            self.enabled = False

    async def shutdown(self) -> None:
        """Cleanup on shutdown."""
        pass

    def get_tools(self) -> list[tuple[ToolDefinition, callable]]:
        """Return calendar tools."""
        return [
            (
                ToolDefinition(
                    name="list_calendar_events",
                    description="List upcoming calendar events",
                    parameters={
                        "type": "object",
                        "properties": {
                            "days": {"type": "integer", "description": "Number of days ahead to check", "default": 7}
                        },
                        "required": [],
                    },
                ),
                self.list_events,
            ),
            (
                ToolDefinition(
                    name="create_calendar_event",
                    description="Create a new calendar event",
                    parameters={
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Event title"},
                            "description": {"type": "string", "description": "Event description"},
                            "start_time": {"type": "string", "description": "ISO 8601 start time"},
                            "end_time": {"type": "string", "description": "ISO 8601 end time"},
                        },
                        "required": ["title", "start_time", "end_time"],
                    },
                ),
                self.create_event,
            ),
        ]

    async def list_events(self, days: int = 7) -> list[dict]:
        """List upcoming calendar events."""
        if not self.enabled or not self.service:
            return []

        try:
            now = datetime.utcnow().isoformat() + "Z"
            time_max = (datetime.utcnow() + timedelta(days=days)).isoformat() + "Z"

            results = await asyncio.to_thread(
                self.service.events()
                .list(
                    calendarId="primary",
                    timeMin=now,
                    timeMax=time_max,
                    maxResults=10,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute
            )

            return [
                {
                    "title": event.get("summary", ""),
                    "start": event.get("start", {}).get("dateTime", ""),
                    "end": event.get("end", {}).get("dateTime", ""),
                }
                for event in results.get("items", [])
            ]
        except Exception as e:
            logger.error(f"List events error: {e}")
            return []

    async def create_event(self, title: str, start_time: str, end_time: str, description: str = "") -> str:
        """Create a new calendar event."""
        if not self.enabled or not self.service:
            return "Calendar not configured"

        try:
            event = {
                "summary": title,
                "description": description,
                "start": {"dateTime": start_time},
                "end": {"dateTime": end_time},
            }

            await asyncio.to_thread(
                self.service.events().insert(calendarId="primary", body=event).execute
            )
            return f"Event '{title}' created"
        except Exception as e:
            logger.error(f"Create event error: {e}")
            return f"Failed to create event: {str(e)}"
