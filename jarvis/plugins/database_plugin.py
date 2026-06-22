
import asyncio

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition


def _format_table(columns: list, rows: list, max_col: int = 40) -> str:
    if not columns:
        return "(no rows)"
    widths = [len(str(c)) for c in columns]
    for r in rows:
        for i, v in enumerate(r):
            widths[i] = min(max_col, max(widths[i], len(str(v))))
    def fmt_row(vals):
        cells = []
        for i, v in enumerate(vals):
            s = str(v)
            if len(s) > max_col:
                s = s[: max_col - 1] + "…"
            cells.append(s.ljust(widths[i]))
        return " | ".join(cells)
    out = [fmt_row(columns), "-+-".join("-" * w for w in widths)]
    for r in rows:
        out.append(fmt_row(r))
    return "\n".join(out)


class DatabasePlugin(Plugin):
    """Query a local SQLite database (or Postgres) safely in read-only mode."""

    def __init__(self):
        super().__init__("database")
        self._tool = None

    def _get(self):
        if self._tool is None:
            from jarvis.brain.db_tool import get_database_tool
            self._tool = get_database_tool()
        return self._tool

    async def initialize(self) -> None:
        logger.info("DatabasePlugin ready")

    async def shutdown(self) -> None:
        try:
            self._get().close()
        except Exception:
            pass

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="db_connect",
                    description=(
                        "Connect to a database. Pass a SQLite file path (e.g. "
                        "C:\\data\\app.db) or a Postgres DSN (postgresql://user:pass@host/db). "
                        "Use when the user says 'open this database', 'connect to my "
                        "sqlite file', 'query my database'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "target": {"type": "string", "description": "SQLite path or Postgres DSN"}
                        },
                        "required": ["target"],
                    },
                ),
                self.db_connect,
            ),
            (
                ToolDefinition(
                    name="db_query",
                    description=(
                        "Run a read-only SQL SELECT query on the connected database "
                        "and return the rows. Write/DDL statements are blocked."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "sql": {"type": "string", "description": "A SELECT query"},
                            "limit": {"type": "integer", "description": "Max rows (default 100)"},
                        },
                        "required": ["sql"],
                    },
                ),
                self.db_query,
            ),
            (
                ToolDefinition(
                    name="db_list_tables",
                    description="List the tables in the connected database.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.db_list_tables,
            ),
            (
                ToolDefinition(
                    name="db_describe_table",
                    description="Show the columns and types of a table.",
                    parameters={
                        "type": "object",
                        "properties": {"table": {"type": "string"}},
                        "required": ["table"],
                    },
                ),
                self.db_describe_table,
            ),
            (
                ToolDefinition(
                    name="db_disconnect",
                    description="Close the current database connection.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.db_disconnect,
            ),
        ]

    async def _run(self, fn, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args))

    async def db_connect(self, target: str) -> str:
        res = await self._run(self._get().connect, target)
        if not res.get("ok"):
            return res.get("error", "Could not connect.")
        tables = await self._run(self._get().list_tables)
        preview = ", ".join(tables[:12]) + (" …" if len(tables) > 12 else "")
        return f"Connected to {res['kind']} database. {len(tables)} table(s): {preview or '(none)'}"

    async def db_query(self, sql: str, limit: int = 100) -> str:
        res = await self._run(self._get().query, sql, int(limit))
        if not res.get("ok"):
            return res.get("error", "Query failed.")
        if not res.get("columns"):
            return f"OK ({res.get('rowcount', 0)} row(s) affected)."
        table = _format_table(res["columns"], res["rows"])
        tail = "\n(truncated)" if res.get("truncated") else ""
        return f"{len(res['rows'])} row(s):\n{table}{tail}"

    async def db_list_tables(self, **_) -> str:
        tables = await self._run(self._get().list_tables)
        if not tables:
            return "No tables (or not connected)."
        return "Tables:\n" + "\n".join(f"  • {t}" for t in tables)

    async def db_describe_table(self, table: str) -> str:
        res = await self._run(self._get().describe, table)
        if not res.get("ok"):
            return res.get("error", "Could not describe table.")
        return _format_table(res["columns"], res["rows"])

    async def db_disconnect(self, **_) -> str:
        await self._run(self._get().close)
        return "Database disconnected."
