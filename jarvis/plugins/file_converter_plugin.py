"""File format converter — images with resize support."""


import asyncio
from pathlib import Path

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition

try:
    from PIL import Image
    _PILLOW = True
except ImportError:
    _PILLOW = False

_SAVE_FORMATS = {
    ".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG",
    ".bmp": "BMP",  ".gif": "GIF",  ".webp": "WEBP",
    ".tiff": "TIFF", ".tif": "TIFF", ".ico": "ICO",
}

_IMAGE_EXTS = set(_SAVE_FORMATS.keys())


def _do_convert(src: Path, dst: Path, quality: int = 90) -> str:
    if not _PILLOW:
        raise RuntimeError("Pillow not installed — run: pip install Pillow")
    fmt = _SAVE_FORMATS.get(dst.suffix.lower())
    if not fmt:
        raise ValueError(f"Unsupported output format: {dst.suffix}")
    img = Image.open(src)
    if fmt == "JPEG" and img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        mask = img.split()[-1] if img.mode in ("RGBA", "LA") else None
        bg.paste(img, mask=mask)
        img = bg
    dst.parent.mkdir(parents=True, exist_ok=True)
    kwargs: dict = {}
    if fmt in ("JPEG", "WEBP"):
        kwargs["quality"] = quality
        kwargs["optimize"] = True
    img.save(str(dst), fmt, **kwargs)
    return str(dst)


class FileConverterPlugin(Plugin):
    """Convert and resize image files between formats (PNG, JPG, WEBP, BMP, TIFF, GIF, ICO)."""

    def __init__(self):
        super().__init__("file_converter")

    async def initialize(self) -> None:
        if not _PILLOW:
            logger.warning("FileConverterPlugin: Pillow missing — run: pip install Pillow")
            self.enabled = False
        else:
            logger.info("FileConverterPlugin ready.")

    async def shutdown(self) -> None:
        pass

    def get_tools(self) -> list[tuple[ToolDefinition, callable]]:
        return [
            (
                ToolDefinition(
                    name="convert_image",
                    description=(
                        "Convert an image file to a different format. "
                        "Supported: PNG, JPG, WEBP, BMP, TIFF, GIF, ICO. "
                        "Handles RGBA → JPEG automatically."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "source_path":   {"type": "string", "description": "Full path to the source image"},
                            "output_format": {"type": "string", "description": "Target format, e.g. 'jpg', 'webp', 'png'"},
                            "output_path":   {"type": "string", "description": "Optional output path (defaults to same folder)"},
                            "quality":       {"type": "integer", "description": "JPEG/WEBP quality 1-95 (default 90)"},
                        },
                        "required": ["source_path", "output_format"],
                    },
                ),
                self.convert_image,
            ),
            (
                ToolDefinition(
                    name="batch_convert_images",
                    description="Convert all images of one format in a folder to another format.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "folder_path":   {"type": "string", "description": "Folder containing source images"},
                            "source_format": {"type": "string", "description": "Source extension, e.g. 'png'"},
                            "output_format": {"type": "string", "description": "Target format, e.g. 'jpg'"},
                            "quality":       {"type": "integer", "description": "JPEG/WEBP quality (default 90)"},
                        },
                        "required": ["folder_path", "source_format", "output_format"],
                    },
                ),
                self.batch_convert_images,
            ),
            (
                ToolDefinition(
                    name="resize_image",
                    description="Resize an image by exact dimensions or a scale factor.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "source_path": {"type": "string", "description": "Path to the source image"},
                            "width":       {"type": "integer", "description": "Target width in pixels"},
                            "height":      {"type": "integer", "description": "Target height in pixels"},
                            "scale":       {"type": "number",  "description": "Scale factor, e.g. 0.5 for half size"},
                            "output_path": {"type": "string",  "description": "Optional output path"},
                        },
                        "required": ["source_path"],
                    },
                ),
                self.resize_image,
            ),
        ]

    async def convert_image(
        self,
        source_path: str,
        output_format: str,
        output_path: str | None = None,
        quality: int = 90,
    ) -> str:
        if not self.enabled:
            return "File converter unavailable — Pillow not installed."
        src = Path(source_path).expanduser()
        if not src.exists():
            return f"File not found: {source_path}"
        ext = "." + output_format.lower().lstrip(".")
        dst = Path(output_path).expanduser() if output_path else src.with_suffix(ext)
        try:
            result = await asyncio.to_thread(_do_convert, src, dst, quality)
            size_kb = Path(result).stat().st_size // 1024
            return f"Saved to {result} ({size_kb} KB)"
        except Exception as e:
            logger.error(f"convert_image: {e}")
            return f"Conversion failed: {e}"

    async def batch_convert_images(
        self,
        folder_path: str,
        source_format: str,
        output_format: str,
        quality: int = 90,
    ) -> str:
        if not self.enabled:
            return "File converter unavailable — Pillow not installed."
        folder = Path(folder_path).expanduser()
        if not folder.is_dir():
            return f"Not a directory: {folder_path}"
        src_ext = "." + source_format.lower().lstrip(".")
        dst_ext = "." + output_format.lower().lstrip(".")
        files = list(folder.glob(f"*{src_ext}"))
        if not files:
            return f"No {source_format.upper()} files found in {folder_path}"
        done, failed = 0, 0
        for f in files:
            try:
                dst = f.with_suffix(dst_ext)
                await asyncio.to_thread(_do_convert, f, dst, quality)
                done += 1
            except Exception as e:
                logger.warning(f"batch_convert: {f.name} — {e}")
                failed += 1
        result = f"Converted {done}/{len(files)} files to {output_format.upper()}"
        if failed:
            result += f" ({failed} failed — check logs)"
        return result

    async def resize_image(
        self,
        source_path: str,
        width: int | None = None,
        height: int | None = None,
        scale: float | None = None,
        output_path: str | None = None,
    ) -> str:
        if not self.enabled:
            return "File converter unavailable — Pillow not installed."
        if not any([width, height, scale]):
            return "Provide at least one of: width, height, or scale."
        src = Path(source_path).expanduser()
        if not src.exists():
            return f"File not found: {source_path}"
        dst = Path(output_path).expanduser() if output_path else src.with_stem(src.stem + "_resized")

        def _resize():
            img = Image.open(src)
            ow, oh = img.size
            if scale:
                nw, nh = int(ow * scale), int(oh * scale)
            elif width and height:
                nw, nh = width, height
            elif width:
                nw, nh = width, int(oh * width / ow)
            else:
                nh = height
                nw = int(ow * height / oh)
            resized = img.resize((nw, nh), Image.LANCZOS)
            dst.parent.mkdir(parents=True, exist_ok=True)
            fmt = _SAVE_FORMATS.get(dst.suffix.lower(), "PNG")
            resized.save(str(dst), fmt)
            return nw, nh

        try:
            w, h = await asyncio.to_thread(_resize)
            return f"Resized to {w}x{h} — saved to {dst}"
        except Exception as e:
            return f"Resize failed: {e}"
