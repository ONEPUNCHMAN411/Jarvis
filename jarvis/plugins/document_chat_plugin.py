
import asyncio

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


class DocumentChatPlugin(Plugin):
    """Chat with your documents: index PDFs/Word/text/code by content and answer
    questions from them with source citations (semantic RAG over a folder)."""

    def __init__(self):
        super().__init__("document_chat")
        self._rag = None

    def _get(self):
        if self._rag is None:
            from jarvis.brain.document_rag import get_document_rag
            self._rag = get_document_rag()
        return self._rag

    async def initialize(self) -> None:
        logger.info("DocumentChatPlugin ready")

    async def shutdown(self) -> None:
        pass

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="index_documents",
                    description=(
                        "Index a document or a whole folder so you can answer "
                        "questions from their contents later. Supports PDF, Word "
                        "(.docx), text, markdown, and code files. Use when the user "
                        "says 'index this folder', 'learn these documents', "
                        "'load my PDFs', or 'remember the files in ...'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Absolute path to a file or folder to index",
                            }
                        },
                        "required": ["path"],
                    },
                ),
                self.index_documents,
            ),
            (
                ToolDefinition(
                    name="ask_documents",
                    description=(
                        "Retrieve the most relevant passages from previously indexed "
                        "documents to answer a question. Returns passages with their "
                        "source file so you can cite them. Use whenever the user asks "
                        "something 'in my documents', 'according to the PDF', or "
                        "'what does the report say about ...'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "The question to answer from the documents",
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "How many passages to retrieve (default 5)",
                            },
                        },
                        "required": ["question"],
                    },
                ),
                self.ask_documents,
            ),
            (
                ToolDefinition(
                    name="list_indexed_documents",
                    description="List the documents currently indexed for Q&A.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.list_indexed_documents,
            ),
            (
                ToolDefinition(
                    name="clear_document_index",
                    description="Delete the entire document index (all indexed files).",
                    parameters={"type": "object", "properties": {}},
                ),
                self.clear_document_index,
            ),
        ]

    async def _run(self, fn, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args))

    async def index_documents(self, path: str) -> str:
        try:
            res = await self._run(self._get().index_path, path)
        except Exception as e:
            return f"Document indexing error: {e}"
        if not res.get("ok"):
            return res.get("error", "Indexing failed.")
        tail = f" ({res['skipped']} skipped)." if res["skipped"] else "."
        return f"Indexed {res['files']} file(s) into {res['chunks']} searchable chunks{tail}"

    async def ask_documents(self, question: str, top_k: int = 5) -> str:
        try:
            hits = await self._run(self._get().query, question, top_k)
        except Exception as e:
            return f"Document query error: {e}"
        if not hits:
            return (
                "No relevant passages found. The document index may be empty — "
                "use index_documents on a file or folder first."
            )
        lines = ["Relevant passages (cite the source file when you answer):"]
        for h in hits:
            src = h["metadata"].get("source", "?")
            text = h["text"].strip().replace("\n", " ")
            if len(text) > 600:
                text = text[:600] + "…"
            lines.append(f"\n[{src}]  (relevance {h['score']:.2f})\n{text}")
        return "\n".join(lines)

    async def list_indexed_documents(self, **_) -> str:
        try:
            srcs = await self._run(self._get().sources)
        except Exception as e:
            return f"Error: {e}"
        if not srcs:
            return "No documents indexed yet."
        lines = [f"{len(srcs)} document(s) indexed:"]
        for s in srcs:
            lines.append(f"  • {s.get('source')}  ({s.get('path')})")
        return "\n".join(lines)

    async def clear_document_index(self, **_) -> str:
        try:
            n = await self._run(self._get().clear)
        except Exception as e:
            return f"Error: {e}"
        return f"Cleared the document index ({n} chunks removed)."
