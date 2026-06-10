import base64
import mimetypes

def load_image_data_url(path: str) -> str | None:
    """Return a base64 data URL for the image at path, or None on failure."""
    try:
        mime, _ = mimetypes.guess_type(path)
        mime = mime or "image/png"
        with open(path, "rb") as fh:
            data = base64.b64encode(fh.read()).decode("ascii")
        return f"data:{mime};base64,{data}"
    except (FileNotFoundError, OSError):
        return None
