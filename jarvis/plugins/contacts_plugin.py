
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class ContactsPlugin(Plugin):
    """A simple contacts book so the assistant can resolve 'email John' or
    'message Sarah on Slack' to real addresses and IDs."""

    def __init__(self):
        super().__init__("contacts")
        self._store = None

    def _get(self):
        if self._store is None:
            from jarvis.brain.contact_store import get_contact_store
            self._store = get_contact_store()
        return self._store

    async def initialize(self) -> None:
        logger.info("ContactsPlugin ready")

    async def shutdown(self) -> None:
        pass

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="add_contact",
                    description=(
                        "Save a person's contact details. Use when the user says "
                        "'add a contact', 'John's email is ...', 'save Sarah's "
                        "Slack id', 'remember my mom's number'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Person's name"},
                            "email": {"type": "string"},
                            "phone": {"type": "string"},
                            "slack": {"type": "string", "description": "Slack channel/user id or #channel"},
                            "discord": {"type": "string", "description": "Discord user/channel id"},
                            "company": {"type": "string"},
                            "notes": {"type": "string"},
                        },
                        "required": ["name"],
                    },
                ),
                self.add_contact,
            ),
            (
                ToolDefinition(
                    name="get_contact",
                    description=(
                        "Look up a saved contact's details by name (fuzzy). Use this "
                        "before emailing/messaging someone by name to get their "
                        "address or id."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"],
                    },
                ),
                self.get_contact,
            ),
            (
                ToolDefinition(
                    name="list_contacts",
                    description="List all saved contacts.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.list_contacts,
            ),
            (
                ToolDefinition(
                    name="update_contact",
                    description="Update one field of a saved contact (email, phone, slack, discord, company, notes).",
                    parameters={
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "field": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["name", "field", "value"],
                    },
                ),
                self.update_contact,
            ),
            (
                ToolDefinition(
                    name="delete_contact",
                    description="Delete a saved contact by name.",
                    parameters={
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"],
                    },
                ),
                self.delete_contact,
            ),
        ]

    @staticmethod
    def _fmt(entry: dict) -> str:
        parts = [entry.get("name", "?")]
        for k in ("email", "phone", "slack", "discord", "company", "notes"):
            if entry.get(k):
                parts.append(f"{k}: {entry[k]}")
        return "  |  ".join(parts)

    async def add_contact(self, name, email="", phone="", slack="",
                          discord="", company="", notes="") -> str:
        entry = self._get().add(name, email=email, phone=phone, slack=slack,
                                discord=discord, company=company, notes=notes)
        return f"Saved contact: {self._fmt(entry)}"

    async def get_contact(self, name) -> str:
        entry = self._get().get(name)
        if not entry:
            return f"No contact found for '{name}'."
        return self._fmt(entry)

    async def list_contacts(self, **_) -> str:
        entries = self._get().list_all()
        if not entries:
            return "No contacts saved yet."
        lines = [f"{len(entries)} contact(s):"]
        for e in entries:
            lines.append(f"  • {self._fmt(e)}")
        return "\n".join(lines)

    async def update_contact(self, name, field, value) -> str:
        ok = self._get().update(name, field.strip().lower(), value)
        return f"Updated {field} for '{name}'." if ok else f"Could not update '{name}' (unknown contact or field)."

    async def delete_contact(self, name) -> str:
        ok = self._get().delete(name)
        return f"Deleted contact '{name}'." if ok else f"No contact found for '{name}'."
