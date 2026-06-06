import json

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSplitter, QTextEdit, QVBoxLayout, QWidget,
)

# One-click installable MCP servers. "configure": True opens the prefilled form
# so the user can paste a key or fix a path before saving; otherwise it installs
# instantly. npx servers need Node.js installed; uvx servers need Python "uv".
_MCP_CATALOG = [
    {
        "name": "filesystem", "title": "Filesystem",
        "desc": "Let JARVIS read & write files in a folder you choose.",
        "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:\\Users"],
        "needs": "Needs Node.js. Set the path arg to the folder you want to expose.",
        "env": {}, "configure": True,
    },
    {
        "name": "brave-search", "title": "Brave Search",
        "desc": "Live web search via the Brave Search API.",
        "command": "npx", "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "needs": "Needs Node.js + a free Brave API key (brave.com/search/api).",
        "env": {"BRAVE_API_KEY": ""}, "configure": True,
    },
    {
        "name": "github", "title": "GitHub",
        "desc": "Repos, issues, pull requests, and code search.",
        "command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"],
        "needs": "Needs Node.js + a GitHub personal access token.",
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": ""}, "configure": True,
    },
    {
        "name": "memory", "title": "Knowledge-Graph Memory",
        "desc": "Persistent knowledge-graph memory for the assistant.",
        "command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"],
        "needs": "Needs Node.js. No keys required.",
        "env": {}, "configure": False,
    },
    {
        "name": "puppeteer", "title": "Puppeteer Browser",
        "desc": "Headless browser automation and screenshots.",
        "command": "npx", "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
        "needs": "Needs Node.js. No keys required.",
        "env": {}, "configure": False,
    },
    {
        "name": "sequential-thinking", "title": "Sequential Thinking",
        "desc": "Structured step-by-step reasoning tool.",
        "command": "npx", "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
        "needs": "Needs Node.js. No keys required.",
        "env": {}, "configure": False,
    },
    {
        "name": "sqlite", "title": "SQLite",
        "desc": "Query and explore a local SQLite database.",
        "command": "uvx", "args": ["mcp-server-sqlite", "--db-path", "C:\\path\\to\\db.sqlite"],
        "needs": "Needs Python 'uv' (uvx). Set the --db-path to your database.",
        "env": {}, "configure": True,
    },
    {
        "name": "time", "title": "Time & Timezone",
        "desc": "Current time and timezone conversions.",
        "command": "uvx", "args": ["mcp-server-time"],
        "needs": "Needs Python 'uv' (uvx). No keys required.",
        "env": {}, "configure": False,
    },
]


class _ProbeWorker(QThread):
    done = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, config: dict):
        super().__init__()
        self._cfg = config

    def run(self):
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            tools = loop.run_until_complete(self._probe())
            loop.close()
            self.done.emit(tools)
        except Exception as exc:
            self.error.emit(str(exc))

    async def _probe(self) -> list:
        from jarvis.mcp.client import MCPClient
        client = MCPClient(self._cfg)
        await client.connect()
        tools = await client.list_tools()
        await client.disconnect()
        return [t["name"] for t in tools]


class _ServerCard(QFrame):
    remove_requested = pyqtSignal(object)
    edit_requested = pyqtSignal(object)

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = dict(cfg)
        self._build()

    def _build(self):
        self.setObjectName("serverCard")
        self.setStyleSheet(
            "#serverCard{background:rgba(59, 158, 255,0.04);"
            "border:1px solid rgba(59, 158, 255,0.14);border-radius:8px;}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 8, 8)

        self._dot = QLabel("●")
        self._dot.setStyleSheet("color: #555a6e; font-size: 9px;")
        row.addWidget(self._dot)

        info = QVBoxLayout()
        server_name = self.cfg.get("name", "?")
        name_lbl = QLabel(f"<b>{server_name}</b>")
        name_lbl.setStyleSheet("color:#E7ECFB;font-size:12px;")
        cmd_str = (self.cfg.get("command", "") + " " + " ".join(self.cfg.get("args", []))).strip()
        self._cmd_lbl = QLabel(cmd_str[:80])
        self._cmd_lbl.setStyleSheet("color:rgba(148,163,184,0.7);font-size:10px;")
        info.addWidget(name_lbl)
        info.addWidget(self._cmd_lbl)
        row.addLayout(info, 1)

        self._enabled_cb = QCheckBox("Enabled")
        self._enabled_cb.setChecked(self.cfg.get("enabled", True))
        self._enabled_cb.stateChanged.connect(lambda s: self.cfg.update({"enabled": bool(s)}))
        row.addWidget(self._enabled_cb)

        edit_btn = QPushButton("Edit")
        edit_btn.setFixedSize(50, 26)
        edit_btn.setStyleSheet(
            "QPushButton{background:rgba(59, 158, 255,0.08);color:rgba(59, 158, 255,0.8);"
            "border:1px solid rgba(59, 158, 255,0.25);border-radius:5px;font-size:10px;}"
            "QPushButton:hover{background:rgba(59, 158, 255,0.2);}"
        )
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self))
        row.addWidget(edit_btn)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(28, 26)
        del_btn.setStyleSheet(
            "QPushButton{background:rgba(239,68,68,0.08);color:rgba(239,68,68,0.7);"
            "border:1px solid rgba(239,68,68,0.2);border-radius:5px;font-size:11px;}"
            "QPushButton:hover{background:rgba(239,68,68,0.2);}"
        )
        del_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        row.addWidget(del_btn)

    def mark_ok(self, tools: list):
        self._dot.setStyleSheet("color:#22c55e;font-size:9px;")
        preview = ", ".join(tools[:4]) + (" ..." if len(tools) > 4 else "")
        self._cmd_lbl.setText(f"{len(tools)} tools: {preview}")

    def mark_err(self, msg: str):
        self._dot.setStyleSheet("color:#ef4444;font-size:9px;")
        self._cmd_lbl.setText(f"Error: {msg[:60]}")


class _AddForm(QWidget):
    saved = pyqtSignal(dict)
    cancelled = pyqtSignal()

    def __init__(self, existing: dict | None = None):
        super().__init__()
        self._existing = existing
        self._worker = None
        self._build()
        if existing:
            self._fill(existing)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        hdr = QLabel("Edit server" if self._existing else "Add MCP server")
        hdr.setStyleSheet("color:rgba(59, 158, 255,0.9);font-size:13px;font-weight:600;")
        layout.addWidget(hdr)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(9)

        def _f(ph):
            w = QLineEdit()
            w.setPlaceholderText(ph)
            w.setStyleSheet(
                "QLineEdit{background:rgba(255,255,255,0.04);color:#E7ECFB;"
                "border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:5px 8px;}"
                "QLineEdit:focus{border-color:rgba(59, 158, 255,0.4);}"
            )
            return w

        self._name = _f("e.g. filesystem")
        self._cmd  = _f("e.g. npx  or  python")
        self._args = _f("-y @modelcontextprotocol/server-filesystem")
        self._env  = QTextEdit()
        self._env.setFixedHeight(60)
        self._env.setPlaceholderText('{"KEY": "value"}  -- optional JSON env vars')
        self._env.setStyleSheet(
            "QTextEdit{background:rgba(255,255,255,0.04);color:#E7ECFB;"
            "border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:5px 8px;}"
        )
        form.addRow("Name", self._name)
        form.addRow("Command", self._cmd)
        form.addRow("Args", self._args)
        form.addRow("Env", self._env)
        layout.addLayout(form)

        hint = QLabel("Args split on spaces. Wrap paths with spaces in quotes.")
        hint.setStyleSheet("color:rgba(148,163,184,0.45);font-size:10px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        row = QHBoxLayout()
        self._test_btn = QPushButton("Test connection")
        self._test_btn.setStyleSheet(
            "QPushButton{background:rgba(59, 158, 255,0.1);color:rgba(59, 158, 255,0.8);"
            "border:1px solid rgba(59, 158, 255,0.3);border-radius:6px;padding:5px 12px;}"
            "QPushButton:hover{background:rgba(59, 158, 255,0.2);}"
        )
        self._test_btn.clicked.connect(self._test)
        row.addWidget(self._test_btn)
        row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            "QPushButton{background:transparent;color:rgba(148,163,184,0.7);"
            "border:1px solid rgba(148,163,184,0.2);border-radius:6px;padding:5px 12px;}"
        )
        cancel_btn.clicked.connect(self.cancelled.emit)
        row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(
            "QPushButton{background:rgba(59, 158, 255,0.85);color:#000;"
            "border:none;border-radius:6px;padding:5px 16px;font-weight:600;}"
            "QPushButton:hover{background:#3B9EFF;}"
        )
        save_btn.clicked.connect(self._save)
        row.addWidget(save_btn)
        layout.addLayout(row)

        self._status = QLabel("")
        self._status.setStyleSheet("color:rgba(148,163,184,0.7);font-size:10px;")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

    def _fill(self, cfg: dict):
        self._name.setText(cfg.get("name", ""))
        self._cmd.setText(cfg.get("command", ""))
        self._args.setText(" ".join(cfg.get("args", [])))
        env = cfg.get("env", {})
        if env:
            self._env.setPlainText(json.dumps(env, indent=2))

    def _build_cfg(self):
        name = self._name.text().strip()
        cmd  = self._cmd.text().strip()
        if not name or not cmd:
            self._status.setText("Name and command are required.")
            return None
        args = self._args.text().strip().split() if self._args.text().strip() else []
        env_raw = self._env.toPlainText().strip()
        env: dict = {}
        if env_raw:
            try:
                env = json.loads(env_raw)
            except json.JSONDecodeError:
                self._status.setText("Env must be valid JSON.")
                return None
        return {"name": name, "command": cmd, "args": args, "env": env, "enabled": True}

    def _test(self):
        cfg = self._build_cfg()
        if not cfg:
            return
        self._test_btn.setEnabled(False)
        self._test_btn.setText("Testing...")
        self._status.setText("")
        self._worker = _ProbeWorker(cfg)
        self._worker.done.connect(self._on_ok)
        self._worker.error.connect(self._on_err)
        self._worker.start()

    def _on_ok(self, tools: list):
        self._test_btn.setEnabled(True)
        self._test_btn.setText("Test connection")
        self._status.setStyleSheet("color:#22c55e;font-size:10px;")
        names = ", ".join(tools[:5])
        self._status.setText(f"Connected! {len(tools)} tools: {names}")

    def _on_err(self, msg: str):
        self._test_btn.setEnabled(True)
        self._test_btn.setText("Test connection")
        self._status.setStyleSheet("color:#ef4444;font-size:10px;")
        self._status.setText(f"Error: {msg}")

    def _save(self):
        cfg = self._build_cfg()
        if cfg:
            self.saved.emit(cfg)


class MCPManagerDialog(QDialog):
    servers_changed = pyqtSignal(list)

    def __init__(self, servers: list, parent=None):
        super().__init__(parent)
        self._servers = [dict(s) for s in servers]
        self._cards: list = []
        self._editing = None
        self.setWindowTitle("MCP Servers")
        self.setMinimumSize(660, 500)
        self.setStyleSheet(
            "QDialog{background:#0d1117;color:#E7ECFB;}"
            "QLabel{color:#E7ECFB;}"
        )
        self._setup_ui()
        self._refresh()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(12)

        trow = QHBoxLayout()
        title = QLabel("MCP Servers")
        title.setStyleSheet("font-size:17px;font-weight:700;color:#f1f5f9;")
        trow.addWidget(title)
        trow.addStretch()
        browse_btn = QPushButton("Browse catalog")
        browse_btn.setStyleSheet(
            "QPushButton{background:rgba(59, 158, 255,0.10);color:#3B9EFF;"
            "border:1px solid rgba(59, 158, 255,0.35);border-radius:7px;padding:7px 14px;font-weight:600;}"
            "QPushButton:hover{background:rgba(59, 158, 255,0.20);}"
        )
        browse_btn.clicked.connect(self._show_catalog)
        trow.addWidget(browse_btn)

        add_btn = QPushButton("+ Add server")
        add_btn.setStyleSheet(
            "QPushButton{background:rgba(59, 158, 255,0.85);color:#000;"
            "border:none;border-radius:7px;padding:7px 16px;font-weight:600;}"
            "QPushButton:hover{background:#3B9EFF;}"
        )
        add_btn.clicked.connect(lambda: self._show_form(None))
        trow.addWidget(add_btn)
        root.addLayout(trow)

        desc = QLabel(
            "Connect JARVIS to external MCP servers — each server's tools become "
            "available to JARVIS automatically. Click 'Browse catalog' to install "
            "popular servers in one click, or '+ Add server' to add your own. "
            "Most need Node.js (for npx) or Python 'uv' (for uvx) installed. "
            "Changes take effect on next launch."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color:rgba(148,163,184,0.7);font-size:11px;")
        root.addWidget(desc)

        self._split = QSplitter(Qt.Orientation.Horizontal)

        list_w = QWidget()
        lv = QVBoxLayout(list_w)
        lv.setContentsMargins(0, 0, 0, 0)
        self._cards_layout = QVBoxLayout()
        self._cards_layout.setSpacing(8)
        inner = QWidget()
        inner.setLayout(self._cards_layout)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        lv.addWidget(scroll)
        self._split.addWidget(list_w)

        self._form_host = QWidget()
        fv = QVBoxLayout(self._form_host)
        fv.setContentsMargins(14, 0, 0, 0)
        self._form_slot = QVBoxLayout()
        fv.addLayout(self._form_slot)
        fv.addStretch()
        self._form_host.setVisible(False)
        self._split.addWidget(self._form_host)
        self._split.setSizes([360, 280])
        root.addWidget(self._split, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        apply_btn = QPushButton("Apply & Close")
        apply_btn.setStyleSheet(
            "QPushButton{background:rgba(59, 158, 255,0.85);color:#000;"
            "border:none;border-radius:7px;padding:7px 18px;font-weight:600;}"
            "QPushButton:hover{background:#3B9EFF;}"
        )
        apply_btn.clicked.connect(self._apply)
        btns.addButton(apply_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        root.addWidget(btns)

    def _refresh(self):
        for card in self._cards:
            self._cards_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        if not self._servers:
            lbl = QLabel("No servers yet.\nClick '+ Add server' to get started.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color:rgba(148,163,184,0.4);font-size:12px;")
            self._cards_layout.addWidget(lbl)
        else:
            for cfg in self._servers:
                card = _ServerCard(cfg)
                card.remove_requested.connect(self._remove)
                card.edit_requested.connect(self._edit)
                self._cards.append(card)
                self._cards_layout.addWidget(card)
        self._cards_layout.addStretch()

    def _show_form(self, existing):
        while self._form_slot.count():
            item = self._form_slot.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        form = _AddForm(existing)
        form.saved.connect(self._on_saved)
        form.cancelled.connect(lambda: self._form_host.setVisible(False))
        self._form_slot.addWidget(form)
        self._form_host.setVisible(True)

    def _show_catalog(self):
        """Show the installable MCP catalog in the side panel."""
        while self._form_slot.count():
            item = self._form_slot.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        panel = QWidget()
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(8)

        hdr = QLabel("Install a server")
        hdr.setStyleSheet("color:rgba(59, 158, 255,0.9);font-size:13px;font-weight:600;")
        pv.addWidget(hdr)

        note = QLabel("One-click install. Servers run on first use via npx/uvx.")
        note.setStyleSheet("color:rgba(148,163,184,0.55);font-size:10px;")
        note.setWordWrap(True)
        pv.addWidget(note)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}")
        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 4, 0)
        iv.setSpacing(8)
        installed = {s.get("name") for s in self._servers}
        for entry in _MCP_CATALOG:
            iv.addWidget(self._build_catalog_card(entry, entry["name"] in installed))
        iv.addStretch()
        scroll.setWidget(inner)
        pv.addWidget(scroll, 1)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            "QPushButton{background:transparent;color:rgba(148,163,184,0.7);"
            "border:1px solid rgba(148,163,184,0.2);border-radius:6px;padding:5px 12px;}"
        )
        close_btn.clicked.connect(lambda: self._form_host.setVisible(False))
        pv.addWidget(close_btn)

        self._form_slot.addWidget(panel)
        self._form_host.setVisible(True)

    def _build_catalog_card(self, entry: dict, installed: bool) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame{background:rgba(59, 158, 255,0.04);"
            "border:1px solid rgba(59, 158, 255,0.12);border-radius:8px;}"
        )
        v = QVBoxLayout(card)
        v.setContentsMargins(12, 9, 12, 10)
        v.setSpacing(4)

        top = QHBoxLayout()
        title = QLabel(f"<b>{entry['title']}</b>")
        title.setStyleSheet("color:#E7ECFB;font-size:12px;border:none;")
        top.addWidget(title)
        top.addStretch()
        btn = QPushButton("Installed" if installed else "Install")
        btn.setEnabled(not installed)
        btn.setFixedHeight(26)
        btn.setStyleSheet(
            "QPushButton{background:rgba(59, 158, 255,0.85);color:#000;border:none;"
            "border-radius:5px;padding:3px 14px;font-size:11px;font-weight:600;}"
            "QPushButton:hover{background:#3B9EFF;}"
            "QPushButton:disabled{background:rgba(45,232,176,0.15);color:#2DE8B0;}"
        )
        btn.clicked.connect(lambda _, e=entry: self._install_from_catalog(e))
        top.addWidget(btn)
        v.addLayout(top)

        desc = QLabel(entry["desc"])
        desc.setStyleSheet("color:rgba(148,163,184,0.8);font-size:11px;border:none;")
        desc.setWordWrap(True)
        v.addWidget(desc)

        needs = QLabel(entry["needs"])
        needs.setStyleSheet("color:rgba(148,163,184,0.5);font-size:10px;border:none;")
        needs.setWordWrap(True)
        v.addWidget(needs)
        return card

    def _install_from_catalog(self, entry: dict):
        cfg = {
            "name": entry["name"],
            "command": entry["command"],
            "args": list(entry["args"]),
            "env": dict(entry.get("env", {})),
            "enabled": True,
        }
        if entry.get("configure"):
            # Needs a key or a path — open the prefilled form so the user can edit.
            self._editing = None
            self._show_form(cfg)
        else:
            if not any(s.get("name") == cfg["name"] for s in self._servers):
                self._servers.append(cfg)
            self._refresh()
            self._show_catalog()  # refresh Install -> Installed state

    def _edit(self, card: _ServerCard):
        self._editing = card
        self._show_form(card.cfg)

    def _on_saved(self, cfg: dict):
        if self._editing:
            idx = self._cards.index(self._editing)
            self._servers[idx] = cfg
            self._editing = None
        else:
            self._servers.append(cfg)
        self._form_host.setVisible(False)
        self._refresh()

    def _remove(self, card: _ServerCard):
        self._servers.pop(self._cards.index(card))
        self._refresh()

    def _apply(self):
        self._servers = [c.cfg for c in self._cards]
        self.servers_changed.emit(self._servers)
        self.accept()
