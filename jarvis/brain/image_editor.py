
from pathlib import Path

_IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}


def remove_background(path: str, out: str | None = None) -> dict:
    try:
        from rembg import remove
    except ImportError:
        return {"ok": False, "error": "Background removal needs: pip install rembg onnxruntime"}
    p = Path(path).expanduser()
    if not p.is_file():
        return {"ok": False, "error": f"Image not found: {path}"}
    try:
        result = remove(p.read_bytes())
        out_path = Path(out).expanduser() if out else p.with_name(p.stem + "_nobg.png")
        out_path.write_bytes(result)
        return {"ok": True, "out": str(out_path)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def batch_remove_background(folder: str) -> dict:
    p = Path(folder).expanduser()
    if not p.is_dir():
        return {"ok": False, "error": f"Not a folder: {folder}"}
    files = [f for f in p.iterdir() if f.is_file() and f.suffix.lower() in _IMG_EXTS]
    if not files:
        return {"ok": False, "error": "No images in that folder."}
    done = failed = 0
    for f in files:
        if remove_background(str(f)).get("ok"):
            done += 1
        else:
            failed += 1
    return {"ok": True, "done": done, "failed": failed, "total": len(files)}


def add_watermark(path: str, text: str, out: str | None = None,
                  opacity: int = 140, position: str = "bottom-right") -> dict:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return {"ok": False, "error": "PIL not available."}
    p = Path(path).expanduser()
    if not p.is_file():
        return {"ok": False, "error": f"Image not found: {path}"}
    try:
        base = Image.open(str(p)).convert("RGBA")
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        try:
            font = ImageFont.truetype("arial.ttf", max(16, base.width // 22))
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        m = 14
        spots = {
            "bottom-right": (base.width - tw - m, base.height - th - m),
            "bottom-left": (m, base.height - th - m),
            "top-right": (base.width - tw - m, m),
            "top-left": (m, m),
            "center": ((base.width - tw) // 2, (base.height - th) // 2),
        }
        pos = spots.get(position, spots["bottom-right"])
        draw.text(pos, text, fill=(255, 255, 255, int(opacity)), font=font)
        merged = Image.alpha_composite(base, overlay)
        out_path = Path(out).expanduser() if out else p.with_name(p.stem + "_wm.png")
        merged.save(str(out_path))
        return {"ok": True, "out": str(out_path)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
