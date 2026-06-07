
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSplitter, QSpinBox, QTextEdit,
    QVBoxLayout, QWidget,
)


class _ProbeWorker(QThread):
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, config: dict):
        super().__init__()
        self._cfg = config

    def run(self):
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(self._probe())
            loop.close()
            self.done.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))

    async def _probe(self) -> str:
        from jarvis.ssh.ssh_client import SSHClient, SSHConfig
        cfg = SSHConfig.from_dict(self._cfg)
        client = SSHClient(cfg)
        await client.connect()
        result = await client.execute("uname -a || ver")
        await client.disconnect()
        return str(result)


class _ServerCard(QFrame):
    remove_requested = pyqtSignal(object)
    edit_requested = pyqtSignal(object)
    connect_requested = pyqtSignal(object)

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = dict(cfg)
        self._connected = False
        self._build()

    def _build(self):
        self.setObjectName("sshCard")
        self.setStyleSheet(
            "#sshCard{background:rgba(59, 158, 255,0.04);"
            "border:1px solid rgba(59, 158, 255,0.14);border-radius:8px;}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 8, 8)

        self._dot = QLabel("●")
        self._dot.setStyleSheet("color:#555a6e;font-size:9px;")
        row.addWidget(self._dot)

        info = QVBoxLayout()
        server_name = self.cfg.get("name", "?")
        host = self.cfg.get("host", "")
        port = self.cfg.get("port", 22)
        user = self.cfg.get("username", "")
        name_lbl = QLabel(f"<b>{server_name}</b>")
        name_lbl.setStyleSheet("color:#E7ECFB;font-size:12px;")
        self._sub_lbl = QLabel(f"{user}@{host}:{port}")
        self._sub_lbl.setStyleSheet("color:rgba(148,163,184,0.7);font-size:10px;")
        info.addWidget(name_lbl)
        info.addWidget(self._sub_lbl)
        row.addLayout(info, 1)

        self._enabled_cb = QCheckBox("Enabled")
        self._enabled_cb.setChecked(self.cfg.get("enabled", True))
        self._enabled_cb.stateChanged.connect(
            lambda s: self.cfg.update({"enabled": bool(s)})
        )
        row.addWidget(self._enabled_cb)

        self._conn_btn = QPushButton("Connect")
        self._conn_btn.setFixedSize(72, 26)
        self._conn_btn.setStyleSheet(
            "QPushButton{background:rgba(34,197,94,0.1);color:rgba(34,197,94,0.8);"
            "border:1px solid rgba(34,197,94,0.25);border-radius:5px;font-size:10px;}"
            "QPushButton:hover{background:rgba(34,197,94,0.22);}"
        )
        self._conn_btn.clicked.connect(lambda: self.connect_requested.emit(self))
        row.addWidget(self._conn_btn)

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

    def mark_connected(self):
        self._connected = True
        self._dot.setStyleSheet("color:#22c55e;font-size:9px;")
        self._conn_btn.setText("Disconnect")
        self._conn_btn.setStyleSheet(
            "QPushButton{background:rgba(239,68,68,0.1);color:rgba(239,68,68,0.8);"
            "border:1px solid rgba(239,68,68,0.25);border-radius:5px;font-size:10px;}"
            "QPushButton:hover{background:rgba(239,68,68,0.22);}"
        )

    def mark_disconnected(self):
        self._connected = False
        self._dot.setStyleSheet("color:#555a6e;font-size:9px;")
        self._conn_btn.setText("Connect")
        self._conn_btn.setStyleSheet(
            "QPushButton{background:rgba(34,197,94,0.1);color:rgba(34,197,94,0.8);"
            "border:1px solid rgba(34,197,94,0.25);border-radius:5px;font-size:10px;}"
            "QPushButton:hover{background:rgba(34,197,94,0.22);}"
        )

    def mark_error(self, msg: str):
        self._dot.setStyleSheet("color:#ef4444;font-size:9px;")
        self._sub_lbl.setText(f"Error: {msg[:50]}")


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

        hdr = QLabel("Edit server" if self._existing else "Add SSH server")
        hdr.setStyleSheet(
            "color:rgba(59, 158, 255,0.9);font-size:13px;font-weight:600;"
        )
        layout.addWidget(hdr)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(9)

        def _f(ph):
            w = QLineEdit()
            w.setPlaceholderText(ph)
            w.setStyleSheet(
                "QLineEdit{background:rgba(255,255,255,0.04);color:#E7ECFB;"
                "border:1px solid rgba(255,255,255,0.1);border-radius:6px;"
                "padding:5px 8px;}"
                "QLineEdit:focus{border-color:rgba(59, 158, 255,0.4);}"
            )
            return w

        self._name = _f("e.g. my-server")
        self._host = _f("192.168.1.10 or example.com")
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(22)
        self._port.setStyleSheet(
            "QSpinBox{background:rgba(255,255,255,0.04);color:#E7ECFB;"
            "border:1px solid rgba(255,255,255,0.1);border-radius:6px;"
            "padding:5px 8px;}"
        )
        self._user = _f("root or ubuntu")
        self._pass = _f("password (leave blank if using key)")
        self._pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._key = _f("/path/to/private_key  (optional)")

        form.addRow("Name", self._name)
        form.addRow("Host", self._host)
        form.addRow("Port", self._port)
        form.addRow("Username", self._user)
        form.addRow("Password", self._pass)
        form.addRow("Key file", self._key)
        layout.addLayout(form)

        hint = QLabel(
            "Use key file OR password. Key takes priority if both are set."
        )
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
            "border:1px solid rgba(148,163,184,0.2);border-radius:6px;"
            "padding:5px 12px;}"
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

        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setFixedHeight(72)
        self._output.setPlaceholderText("Test output will appear here...")
        self._output.setStyleSheet(
            "QTextEdit{background:rgba(0,0,0,0.3);color:#8A94B8;"
            "border:1px solid rgba(255,255,255,0.06);border-radius:6px;"
            "padding:6px;font-family:monospace;font-size:10px;}"
        )
        layout.addWidget(self._output)

    def _fill(self, cfg: dict):
        self._name.setText(cfg.get("name", ""))
        self._host.setText(cfg.get("host", ""))
        self._port.setValue(cfg.get("port", 22))
        self._user.setText(cfg.get("username", ""))
        self._pass.setText(cfg.get("password", ""))
        self._key.setText(cfg.get("key_path", ""))

    def _build_cfg(self) -> dict | None:
        name = self._name.text().strip()
        host = self._host.text().strip()
        if not name or not host:
            self._status.setText("Name and host are required.")
            return None
        return {
            "name": name,
            "host": host,
            "port": self._port.value(),
            "username": self._user.text().strip(),
            "password": self._pass.text(),
            "key_path": self._key.text().strip(),
            "enabled": True,
        }

    def _test(self):
        cfg = self._build_cfg()
        if not cfg:
            return
        self._test_btn.setEnabled(False)
        self._test_btn.setText("Testing...")
        self._status.setText("")
        self._output.clear()
        self._worker = _ProbeWorker(cfg)
        self._worker.done.connect(self._on_ok)
        self._worker.error.connect(self._on_err)
        self._worker.start()

    def _on_ok(self, output: str):
        self._test_btn.setEnabled(True)
        self._test_btn.setText("Test connection")
        self._status.setStyleSheet("color:#22c55e;font-size:10px;")
        self._status.setText("Connected successfully!")
        self._output.setPlainText(output)

    def _on_err(self, msg: str):
        self._test_btn.setEnabled(True)
        self._test_btn.setText("Test connection")
        self._status.setStyleSheet("color:#ef4444;font-size:10px;")
        self._status.setText(f"Error: {msg}")

    def _save(self):
        cfg = self._build_cfg()
        if cfg:
            self.saved.emit(cfg)


class SSHManagerDialog(QDialog):
    servers_changed = pyqtSignal(list)

    def __init__(self, servers: list, parent=None):
        super().__init__(parent)
        self._servers = [dict(s) for s in servers]
        self._cards: list = []
        self._editing = None
        self.setWindowTitle("SSH Servers")
        self.setMinimumSize(700, 520)
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
        title = QLabel("SSH Servers")
        title.setStyleSheet("font-size:17px;font-weight:700;color:#f1f5f9;")
        trow.addWidget(title)
        trow.addStretch()
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
            "Connect JARVIS to SSH servers. JARVIS can execute commands, "
            "read and write files, and manage remote environments via these connections."
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
        self._split.setSizes([360, 320])
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
            lbl = QLabel("No SSH servers yet.\nClick '+ Add server' to get started.")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("color:rgba(148,163,184,0.4);font-size:12px;")
            self._cards_layout.addWidget(lbl)
        else:
            for cfg in self._servers:
                card = _ServerCard(cfg)
                card.remove_requested.connect(self._remove)
                card.edit_requested.connect(self._edit)
                card.connect_requested.connect(self._toggle_connect)
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

    def _toggle_connect(self, card: _ServerCard):
        import asyncio
        from jarvis.ssh.ssh_manager import SSHManager
        mgr = SSHManager()
        client = mgr.get_client(card.cfg.get("name", ""))
        if client is None:
            return

        async def _do():
            if client.is_connected:
                await client.disconnect()
                card.mark_disconnected()
            else:
                try:
                    await client.connect()
                    card.mark_connected()
                except Exception as e:
                    card.mark_error(str(e))

        loop = asyncio.new_event_loop()
        loop.run_until_complete(_do())
        loop.close()

    def _apply(self):
        self._servers = [c.cfg for c in self._cards]
        self.servers_changed.emit(self._servers)
        self.accept()
