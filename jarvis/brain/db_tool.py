
import re
import sqlite3
import threading
from pathlib import Path

# Block writes/DDL so the query tool stays read-only by default.
_WRITE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|replace|attach|pragma|grant|revoke)\b",
    re.IGNORECASE,
)


class DatabaseTool:
    """Connect to a local SQLite file (or a Postgres DSN if psycopg is installed)
    and run read-only queries."""

    def __init__(self):
        self._conn = None
        self._kind = None       # 'sqlite' | 'postgres'
        self._target = ""
        self._lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return self._conn is not None

    def connect(self, target: str) -> dict:
        target = (target or "").strip()
        if not target:
            return {"ok": False, "error": "Provide a SQLite file path or a Postgres DSN."}
        with self._lock:
            self._close_locked()
            if target.startswith("postgres://") or target.startswith("postgresql://"):
                driver = None
                try:
                    import psycopg2 as driver
                except ImportError:
                    try:
                        import psycopg as driver
                    except ImportError:
                        return {"ok": False, "error": "Postgres driver missing. Run: pip install psycopg2-binary"}
                try:
                    self._conn = driver.connect(target)
                    self._kind = "postgres"
                except Exception as e:
                    return {"ok": False, "error": f"Could not connect: {e}"}
            else:
                p = Path(target).expanduser()
                if not p.exists():
                    return {"ok": False, "error": f"SQLite file not found: {target}"}
                try:
                    self._conn = sqlite3.connect(str(p), check_same_thread=False)
                    self._kind = "sqlite"
                except Exception as e:
                    return {"ok": False, "error": f"Could not open database: {e}"}
            self._target = target
            return {"ok": True, "kind": self._kind}

    def _close_locked(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = None
        self._kind = None

    def close(self) -> None:
        with self._lock:
            self._close_locked()

    def _execute(self, sql: str, params=(), limit: int = 200) -> dict:
        if self._conn is None:
            return {"ok": False, "error": "Not connected. Use db_connect first."}
        with self._lock:
            try:
                cur = self._conn.cursor()
                cur.execute(sql, params)
                if cur.description is None:
                    self._conn.commit()
                    return {"ok": True, "columns": [], "rows": [], "rowcount": cur.rowcount}
                cols = [d[0] for d in cur.description]
                rows = cur.fetchmany(max(1, int(limit)))
                return {
                    "ok": True,
                    "columns": cols,
                    "rows": [list(r) for r in rows],
                    "truncated": len(rows) >= limit,
                }
            except Exception as e:
                return {"ok": False, "error": str(e)}

    def query(self, sql: str, limit: int = 200) -> dict:
        if _WRITE.search(sql or ""):
            return {"ok": False, "error": "Read-only mode: write/DDL statements are blocked."}
        return self._execute(sql, (), limit)

    def list_tables(self) -> list:
        if self._kind == "sqlite":
            q = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        else:
            q = ("SELECT table_name FROM information_schema.tables "
                 "WHERE table_schema='public' ORDER BY table_name")
        r = self._execute(q)
        return [row[0] for row in r["rows"]] if r.get("ok") else []

    def describe(self, table: str) -> dict:
        if self._kind == "sqlite":
            return self._execute(f"PRAGMA table_info({table})")
        return self._execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name=%s ORDER BY ordinal_position",
            (table,),
        )


_instance: "DatabaseTool | None" = None


def get_database_tool() -> "DatabaseTool":
    global _instance
    if _instance is None:
        _instance = DatabaseTool()
    return _instance
