
import time
from pathlib import Path


def _out_dir() -> Path:
    d = Path.home() / ".jarvis" / "qr"
    d.mkdir(parents=True, exist_ok=True)
    return d


def generate_qr(data: str, out: str | None = None) -> dict:
    try:
        import qrcode
    except ImportError:
        return {"ok": False, "error": "QR generation needs: pip install qrcode"}
    try:
        img = qrcode.make(data)
        out_path = Path(out).expanduser() if out else _out_dir() / f"qr_{int(time.time() * 1000)}.png"
        img.save(str(out_path))
        return {"ok": True, "out": str(out_path)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def read_qr_image(path: str) -> dict:
    try:
        from pyzbar.pyzbar import decode
        from PIL import Image
    except ImportError:
        return {"ok": False, "error": "QR reading needs: pip install pyzbar"}
    p = Path(path).expanduser()
    if not p.is_file():
        return {"ok": False, "error": f"Image not found: {path}"}
    try:
        results = decode(Image.open(str(p)))
        return {"ok": True, "found": [r.data.decode("utf-8", "replace") for r in results]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def read_qr_screen(x=None, y=None, w=None, h=None) -> dict:
    try:
        from pyzbar.pyzbar import decode
        from PIL import Image
        import mss
    except ImportError:
        return {"ok": False, "error": "QR reading needs: pip install pyzbar"}
    try:
        with mss.mss() as sct:
            if None in (x, y, w, h):
                bbox = sct.monitors[1]
            else:
                bbox = {"left": int(x), "top": int(y), "width": int(w), "height": int(h)}
            shot = sct.grab(bbox)
            img = Image.frombytes("RGB", shot.size, shot.rgb)
        results = decode(img)
        return {"ok": True, "found": [r.data.decode("utf-8", "replace") for r in results]}
    except Exception as e:
        return {"ok": False, "error": str(e)}
