from pathlib import Path


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".heic"}
_PDF_EXT = ".pdf"
_DOC_EXTS = {".docx", ".doc", ".txt", ".md", ".rtf", ".odt"}


def _read_image_hint(path: Path) -> str:
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        img = Image.open(path)
        exif_data = img._getexif()
        if exif_data:
            tags = {TAGS.get(k, k): v for k, v in exif_data.items()}
            date = tags.get("DateTimeOriginal") or tags.get("DateTime", "")
            camera = tags.get("Model", "")
            parts = []
            if date:
                parts.append(f"taken {str(date)[:10]}")
            if camera:
                parts.append(f"camera: {camera}")
            if parts:
                return "; ".join(parts)
        return f"{img.width}x{img.height} {img.mode}"
    except Exception:
        return ""


def _read_pdf_hint(path: Path) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            text = ""
            for page in pdf.pages[:2]:
                text += (page.extract_text() or "") + " "
            return text[:400].strip()
    except Exception:
        pass
    try:
        import fitz
        doc = fitz.open(str(path))
        text = ""
        for i, page in enumerate(doc):
            if i >= 2:
                break
            text += page.get_text() + " "
        doc.close()
        return text[:400].strip()
    except Exception:
        return ""


def _read_doc_hint(path: Path) -> str:
    try:
        ext = path.suffix.lower()
        if ext in {".txt", ".md", ".rtf"}:
            return path.read_text(errors="ignore")[:300].strip()
        if ext == ".docx":
            from docx import Document
            doc = Document(str(path))
            text = " ".join(p.text for p in doc.paragraphs[:10])
            return text[:300].strip()
    except Exception:
        pass
    return ""


class BatchRenamer:
    def scan(self, folder: str, extensions: list | None = None) -> list[dict]:
        root = Path(folder).expanduser()
        if not root.is_dir():
            return []
        results = []
        for p in sorted(root.iterdir()):
            if not p.is_file():
                continue
            ext = p.suffix.lower()
            if extensions and ext not in [e.lower() for e in extensions]:
                continue
            stat = p.stat()
            hint = ""
            if ext in _IMAGE_EXTS:
                hint = _read_image_hint(p)
            elif ext == _PDF_EXT:
                hint = _read_pdf_hint(p)
            elif ext in _DOC_EXTS:
                hint = _read_doc_hint(p)
            results.append({
                "path": str(p),
                "name": p.name,
                "stem": p.stem,
                "ext": ext,
                "size_kb": round(stat.st_size / 1024, 1),
                "content_hint": hint,
            })
        return results

    def apply(self, proposals: list[dict]) -> dict:
        renamed, skipped, errors = [], [], []
        for p in proposals:
            src = Path(p["src"])
            dst = Path(p["dst"])
            if not src.exists():
                skipped.append(p.get("src", "?"))
                continue
            if dst.exists():
                errors.append(f"{dst.name} already exists — skipped")
                continue
            try:
                src.rename(dst)
                renamed.append(f"{src.name} → {dst.name}")
            except Exception as e:
                errors.append(f"{src.name}: {e}")
        return {"renamed": renamed, "skipped": skipped, "errors": errors}


_renamer: BatchRenamer | None = None


def get_batch_renamer() -> BatchRenamer:
    global _renamer
    if _renamer is None:
        _renamer = BatchRenamer()
    return _renamer
