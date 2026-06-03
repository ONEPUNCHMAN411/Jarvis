from dataclasses import dataclass

@dataclass(frozen=True)
class OverlayGeometry:
    x: int
    y: int
    width: int
    height: int

def compute_overlay_geometry(
    screen_width: int,
    screen_height: int,
    orb_size: int,
    mode: str,
    margin: int = 20,
) -> OverlayGeometry:
    resolved_mode = mode if mode in {"floating", "smart_overlay", "docked"} else "floating"
    width = int(orb_size)
    height = int(orb_size)

    if resolved_mode == "docked":
        x = max(0, screen_width - width)
        y = max(margin, screen_height - height - max(margin * 3, 64))
        return OverlayGeometry(x=x, y=y, width=width, height=height)

    x = max(margin, screen_width - width - max(margin * 2, 44))
    y = max(margin, screen_height - height - max(margin * 4, 92))
    return OverlayGeometry(x=x, y=y, width=width, height=height)
