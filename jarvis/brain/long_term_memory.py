
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

try:
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False

_MEMORY_MARKER = "[Memories from past conversations]"


class LongTermMemory:
    """ChromaDB-backed vector store for long-term memories."""

    def __init__(self, persist_dir: str = "~/.jarvis/ltm"):
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
            name="memories",
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"LongTermMemory initialized at {path} ({self._col.count()} memories)")

    def add(self, text: str, metadata: dict | None = None) -> str:
        mid = str(uuid.uuid4())
        meta = {"created": datetime.now(timezone.utc).isoformat(), **(metadata or {})}
        self._col.add(documents=[text], metadatas=[meta], ids=[mid])
        logger.debug(f"LTM stored [{mid[:8]}]: {text[:60]}")
        return mid

    def search(self, query: str, top_k: int = 5, threshold: float = 0.25) -> list[dict]:
        n = min(top_k, self._col.count())
        if n == 0:
            return []
        results = self._col.query(query_texts=[query], n_results=n)
        out: list[dict] = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            score = 1.0 - dist
            if score >= threshold:
                out.append({"text": doc, "metadata": meta, "score": round(score, 4)})
        out.sort(key=lambda x: x["score"], reverse=True)
        return out

    def delete(self, memory_id: str) -> bool:
        try:
            self._col.delete(ids=[memory_id])
            return True
        except Exception as e:
            logger.warning(f"LTM delete failed: {e}")
            return False

    def list_all(self, limit: int = 200) -> list[dict]:
        res = self._col.get(limit=limit)
        return [
            {"id": i, "text": d, "metadata": m}
            for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])
        ]

    def count(self) -> int:
        return self._col.count()

    def inject_into_messages(self, messages: list[dict], top_k: int = 4) -> list[dict]:
        query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                query = content if isinstance(content, str) else str(content)
                break
        if not query:
            return messages
        hits = self.search(query, top_k=top_k)
        if not hits:
            return messages
        block = _MEMORY_MARKER + "\n" + "\n".join(f"- {h['text']}" for h in hits)
        result = list(messages)
        if result and result[0].get("role") == "system":
            existing = result[0].get("content", "")
            # Strip any previously-injected block before re-injecting
            if existing.startswith(_MEMORY_MARKER):
                _, _, existing = existing.partition("\n\n")
            result[0] = {**result[0], "content": block + "\n\n" + existing}
        else:
            result.insert(0, {"role": "system", "content": block})
        return result


_instance: LongTermMemory | None = None
_instance_lock = threading.Lock()


def get_long_term_memory() -> LongTermMemory:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = LongTermMemory()
    return _instance
