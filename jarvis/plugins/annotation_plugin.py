
from loguru import logger
from PyQt6.QtCore import QTimer
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class AnnotationPlugin(Plugin):
    """Draw on the screen — arrows, boxes, highlight points, and labels — to
    visually point things out. Coordinates are global screen pixels; take a
    screenshot first to find them."""

    def __init__(self):
        super().__init__("annotation")

    async def initialize(self) -> None:
        logger.info("AnnotationPlugin ready")

    async def shutdown(self) -> None:
        pass

    def _marshal(self, fn_name: str, **kwargs) -> None:
        # Touch the Qt widget on the GUI thread (same pattern as the doc viewer).
        from jarvis.control.screen_annotator import get_screen_annotator
        QTimer.singleShot(
            0, lambda: getattr(get_screen_annotator(), fn_name)(**kwargs)
        )

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="annotate_arrow",
                    description=(
                        "Draw an arrow on the screen from one point to another to "
                        "point something out. Coordinates are screen pixels. Use "
                        "when the user says 'point at ...', 'show me where ...', "
                        "'draw an arrow to the button'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "x1": {"type": "integer", "description": "Arrow start X (tail)"},
                            "y1": {"type": "integer", "description": "Arrow start Y (tail)"},
                            "x2": {"type": "integer", "description": "Arrow end X (head/target)"},
                            "y2": {"type": "integer", "description": "Arrow end Y (head/target)"},
                            "color": {"type": "string", "description": "blue|green|amber|red|white"},
                            "label": {"type": "string", "description": "Optional text label"},
                        },
                        "required": ["x1", "y1", "x2", "y2"],
                    },
                ),
                self.annotate_arrow,
            ),
            (
                ToolDefinition(
                    name="annotate_box",
                    description=(
                        "Draw a highlight rectangle around a screen region (x,y is "
                        "the top-left corner). Use to frame a button, field, or area."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "x": {"type": "integer"}, "y": {"type": "integer"},
                            "width": {"type": "integer"}, "height": {"type": "integer"},
                            "color": {"type": "string", "description": "blue|green|amber|red|white"},
                            "label": {"type": "string", "description": "Optional text label"},
                        },
                        "required": ["x", "y", "width", "height"],
                    },
                ),
                self.annotate_box,
            ),
            (
                ToolDefinition(
                    name="annotate_point",
                    description=(
                        "Drop a pulsing highlight dot at a screen point to draw the "
                        "eye to an exact spot."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "x": {"type": "integer"}, "y": {"type": "integer"},
                            "color": {"type": "string", "description": "blue|green|amber|red|white"},
                            "label": {"type": "string", "description": "Optional text label"},
                        },
                        "required": ["x", "y"],
                    },
                ),
                self.annotate_point,
            ),
            (
                ToolDefinition(
                    name="annotate_label",
                    description="Place a text label at a screen point.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "x": {"type": "integer"}, "y": {"type": "integer"},
                            "text": {"type": "string"},
                            "color": {"type": "string", "description": "blue|green|amber|red|white"},
                        },
                        "required": ["x", "y", "text"],
                    },
                ),
                self.annotate_label,
            ),
            (
                ToolDefinition(
                    name="clear_annotations",
                    description="Remove all on-screen annotations immediately.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.clear_annotations,
            ),
        ]

    async def annotate_arrow(self, x1, y1, x2, y2, color="blue", label="") -> str:
        self._marshal("add_arrow", x1=int(x1), y1=int(y1), x2=int(x2), y2=int(y2),
                      color=color, label=label)
        return f"Drew an arrow to ({x2}, {y2})."

    async def annotate_box(self, x, y, width, height, color="blue", label="") -> str:
        self._marshal("add_box", x=int(x), y=int(y), w=int(width), h=int(height),
                      color=color, label=label)
        return f"Highlighted the region at ({x}, {y}) {width}x{height}."

    async def annotate_point(self, x, y, color="amber", label="") -> str:
        self._marshal("add_point", x=int(x), y=int(y), color=color, label=label)
        return f"Marked the point ({x}, {y})."

    async def annotate_label(self, x, y, text, color="white") -> str:
        self._marshal("add_label", x=int(x), y=int(y), text=text, color=color)
        return f"Placed label '{text}' at ({x}, {y})."

    async def clear_annotations(self, **_) -> str:
        self._marshal("clear")
        return "Cleared all annotations."
