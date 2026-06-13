
from pathlib import Path

from loguru import logger
from PyQt6.QtCore import QTimer
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class DocumentPlugin(Plugin):
    """Open files, PDFs, images, and text in the side panel viewer."""

    def __init__(self):
        super().__init__("document_viewer")

    async def initialize(self) -> None:
        logger.info("DocumentPlugin ready")

    async def shutdown(self) -> None:
        pass

    def get_tools(self) -> list[tuple[ToolDefinition, callable]]:
        return [
            (
                ToolDefinition(
                    name="open_document",
                    description=(
                        "Open a file (PDF, image, text, markdown, code) in the animated "
                        "document viewer panel. It slides in from the right of the screen."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Absolute path to the file",
                            },
                            "title": {
                                "type": "string",
                                "description": "Optional display title for the tab",
                            },
                        },
                        "required": ["path"],
                    },
                ),
                self.open_document,
            ),
            (
                ToolDefinition(
                    name="close_document_viewer",
                    description="Slide the document viewer panel closed.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.close_viewer,
            ),
            (
                ToolDefinition(
                    name="toggle_document_viewer",
                    description="Show or hide the document viewer panel.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.toggle_viewer,
            ),
        ]

    async def open_document(self, path: str, title: str | None = None) -> str:
        p = Path(path).expanduser()
        if not p.exists():
            return f"File not found: {path}"
        try:
            from jarvis.ui.document_viewer import get_document_viewer
            viewer = get_document_viewer()
            # Must run on Qt main thread — marshal via QTimer
            QTimer.singleShot(0, lambda: viewer.open_document(str(p), title=title or p.name))
            return f"Opened '{p.name}' in the document viewer."
        except Exception as e:
            logger.exception("DocumentPlugin.open_document failed")
            return f"Could not open document: {e}"

    async def close_viewer(self) -> str:
        try:
            from jarvis.ui.document_viewer import get_document_viewer
            viewer = get_document_viewer()
            if viewer.is_visible:
                QTimer.singleShot(0, viewer.slide_out)
                return "Document viewer closed."
            return "Document viewer is already hidden."
        except Exception as e:
            return f"Error: {e}"

    async def toggle_viewer(self) -> str:
        try:
            from jarvis.ui.document_viewer import get_document_viewer
            QTimer.singleShot(0, get_document_viewer().toggle)
            return "Document viewer toggled."
        except Exception as e:
            return f"Error: {e}"
