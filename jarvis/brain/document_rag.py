
import hashlib
import threading
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

try:
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False

_TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".py", ".js", ".ts", ".json", ".html", ".css",
    ".java", ".c", ".cpp", ".h", ".rs", ".go", ".rb", ".sh", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".csv", ".log", ".xml", ".sql",
}


def _read_pdf(path: Path) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return ""
    parts: list[str] = []
    with fitz.open(str(path)) as doc:
        for i, page in enumerate(doc):
            text = page.get_text().strip()
            if text:
                parts.append(f"[page {i + 1}]\n{text}")
    return "\n\n".join(parts)


def _read_docx(path: Path) -> str:
    try:
        import docx  # python-docx
    except ImportError:
        return ""
    document = docx.Document(str(path))
    return "\n".join(p.text for p in document.paragraphs if p.text.strip())


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _extract(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _read_pdf(path)
    if ext == ".docx":
        return _read_docx(path)
    if ext in _TEXT_EXTS:
        return _read_text(path)
    return ""


def _chunk(text: str, size: int = 1100, overlap: int = 150) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    start, n = 0, len(text)
    while start < n:
        end = min(start + size, n)
        chunks.append(text[start:end])
        if end >= n:
            break
        start = end - overlap
    return chunks


class DocumentRAG:
    """ChromaDB-backed semantic index over document CONTENT, for Q&A with citations."""

    SUPPORTED = sorted({".pdf", ".docx"} | _TEXT_EXTS)

    def __init__(self, persist_dir: str = "~/.jarvis/docs_index"):
        if not _CHROMA_AVAILABLE:
            raise ImportError(
                "chromadb and sentence-transformers are required. "
                "Run: pip install chromadb sentence-transformers"
            )
        path = Path(persist_dir).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(path))
        self._ef = SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2", device="cpu"
        )
        self._col = self._client.get_or_create_collection(
            name="documents",
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"DocumentRAG ready at {path} ({self._col.count()} chunks)")

    def _doc_id(self, path: Path) -> str:
        return hashlib.md5(str(path.resolve()).encode("utf-8")).hexdigest()[:12]

    def index_path(self, target: str) -> dict:
        p = Path(target).expanduser()
        if not p.exists():
            return {"ok": False, "error": f"Path not found: {target}"}
        if p.is_file():
            files = [p]
        else:
            files = [
                f for f in p.rglob("*")
                if f.is_file() and f.suffix.lower() in self.SUPPORTED
            ]
        if not files:
            return {"ok": False, "error": "No supported documents found at that path."}
        indexed = chunks_total = skipped = 0
        for f in files:
            try:
                text = _extract(f)
                if not text.strip():
                    skipped += 1
                    continue
                doc_id = self._doc_id(f)
                try:
                    self._col.delete(where={"doc_id": doc_id})
                except Exception:
                    pass
                chunks = _chunk(text)
                ids = [f"{doc_id}-{i}" for i in range(len(chunks))]
                metas = [
                    {
                        "doc_id": doc_id,
                        "source": f.name,
                        "path": str(f),
                        "chunk": i,
                        "indexed": datetime.now(timezone.utc).isoformat(),
                    }
                    for i in range(len(chunks))
                ]
                self._col.add(documents=chunks, metadatas=metas, ids=ids)
                indexed += 1
                chunks_total += len(chunks)
            except Exception as e:
                logger.warning(f"DocumentRAG index failed for {f}: {e}")
                skipped += 1
        return {"ok": True, "files": indexed, "chunks": chunks_total, "skipped": skipped}

    def query(self, question: str, top_k: int = 5) -> list[dict]:
        n = min(top_k, self._col.count())
        if n == 0:
            return []
        res = self._col.query(query_texts=[question], n_results=n)
        out: list[dict] = []
        for doc, meta, dist in zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            out.append({"text": doc, "metadata": meta, "score": round(1.0 - dist, 4)})
        return out

    def sources(self) -> list[dict]:
        res = self._col.get(include=["metadatas"])
        seen: dict[str, dict] = {}
        for meta in res.get("metadatas", []) or []:
            did = meta.get("doc_id")
            if did and did not in seen:
                seen[did] = {"source": meta.get("source"), "path": meta.get("path")}
        return list(seen.values())

    def clear(self) -> int:
        count = self._col.count()
        self._client.delete_collection("documents")
        self._col = self._client.get_or_create_collection(
            name="documents",
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )
        return count

    def count(self) -> int:
        return self._col.count()


_instance: "DocumentRAG | None" = None
_lock = threading.Lock()


def get_document_rag() -> "DocumentRAG":
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = DocumentRAG()
    return _instance
