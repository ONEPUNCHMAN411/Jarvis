"""System resource monitor with configurable alert thresholds and background polling."""


import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False


@dataclass
class MonitorConfig:
    cpu_warn: float = 85.0
    ram_warn: float = 85.0
    disk_warn: float = 90.0
    poll_interval: float = 5.0
    disk_path: str = "C:\\"


@dataclass
class ResourceSnapshot:
    timestamp: str
    cpu_pct: float
    ram_pct: float
    ram_used_gb: float
    ram_total_gb: float
    disk_pct: float
    disk_free_gb: float
    top_processes: list[dict] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)


def _take_snapshot(cfg: MonitorConfig) -> ResourceSnapshot:
    if not _PSUTIL:
        return ResourceSnapshot(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            cpu_pct=0.0, ram_pct=0.0, ram_used_gb=0.0,
            ram_total_gb=0.0, disk_pct=0.0, disk_free_gb=0.0,
            alerts=["psutil not installed — run: pip install psutil"],
        )

    cpu  = psutil.cpu_percent(interval=0.5)
    ram  = psutil.virtual_memory()
    disk = psutil.disk_usage(cfg.disk_path)

    top: list[dict] = []
    try:
        procs = sorted(
            psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
            key=lambda p: p.info.get("cpu_percent") or 0,
            reverse=True,
        )[:5]
        for p in procs:
            top.append({
                "pid":  p.info["pid"],
                "name": p.info["name"],
                "cpu":  round(p.info.get("cpu_percent") or 0, 1),
                "ram":  round(p.info.get("memory_percent") or 0, 1),
            })
    except Exception:
        pass

    alerts: list[str] = []
    if cpu >= cfg.cpu_warn:
        alerts.append(f"CPU at {cpu:.1f}% (limit {cfg.cpu_warn:.0f}%)")
    if ram.percent >= cfg.ram_warn:
        alerts.append(f"RAM at {ram.percent:.1f}% (limit {cfg.ram_warn:.0f}%)")
    if disk.percent >= cfg.disk_warn:
        alerts.append(f"Disk at {disk.percent:.1f}% (limit {cfg.disk_warn:.0f}%)")

    return ResourceSnapshot(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        cpu_pct=cpu,
        ram_pct=ram.percent,
        ram_used_gb=ram.used / 1e9,
        ram_total_gb=ram.total / 1e9,
        disk_pct=disk.percent,
        disk_free_gb=disk.free / 1e9,
        top_processes=top,
        alerts=alerts,
    )


def _format_snapshot(snap: ResourceSnapshot, verbose: bool = False) -> str:
    lines = [
        f"**System Resources** ({snap.timestamp})",
        f"CPU:  {snap.cpu_pct:.1f}%",
        f"RAM:  {snap.ram_pct:.1f}%  ({snap.ram_used_gb:.1f} / {snap.ram_total_gb:.1f} GB)",
        f"Disk: {snap.disk_pct:.1f}%  ({snap.disk_free_gb:.1f} GB free)",
    ]
    if verbose and snap.top_processes:
        lines.append("\nTop processes by CPU:")
        for p in snap.top_processes:
            lines.append(f"  {p['name']:<22} CPU {p['cpu']:5.1f}%  RAM {p['ram']:4.1f}%")
    if snap.alerts:
        lines.append("\n⚠ Alerts:")
        for a in snap.alerts:
            lines.append(f"  • {a}")
    return "\n".join(lines)


class _BackgroundMonitor:
    def __init__(self, cfg: MonitorConfig, on_alert: Callable | None):
        self._cfg = cfg
        self._on_alert = on_alert
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: ResourceSnapshot | None = None
        self._lock = threading.Lock()

    @property
    def last(self) -> ResourceSnapshot | None:
        with self._lock:
            return self._last

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.wait(self._cfg.poll_interval):
            snap = _take_snapshot(self._cfg)
            with self._lock:
                self._last = snap
            if snap.alerts and self._on_alert:
                try:
                    self._on_alert(snap)
                except Exception:
                    pass


class SystemMonitorPlugin(Plugin):
    """Real-time CPU, RAM, and disk monitoring with configurable alert thresholds."""

    def __init__(self):
        super().__init__("system_monitor")
        self._cfg = MonitorConfig()
        self._monitor: _BackgroundMonitor | None = None

    async def initialize(self) -> None:
        if not _PSUTIL:
            logger.warning("SystemMonitorPlugin: psutil not installed — run: pip install psutil")
            self.enabled = False
            return
        self._monitor = _BackgroundMonitor(self._cfg, on_alert=self._on_alert)
        self._monitor.start()
        logger.info("SystemMonitorPlugin started background polling.")

    async def shutdown(self) -> None:
        if self._monitor:
            self._monitor.stop()

    def _on_alert(self, snap: ResourceSnapshot) -> None:
        logger.warning(f"SystemMonitor alert: {', '.join(snap.alerts)}")

    def get_tools(self) -> list[tuple[ToolDefinition, callable]]:
        return [
            (
                ToolDefinition(
                    name="get_system_status",
                    description="Get current CPU, RAM, and disk usage. Pass verbose=true to include top processes.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "verbose": {"type": "boolean",
                                        "description": "Include top processes by CPU usage"},
                        },
                    },
                ),
                self.get_system_status,
            ),
            (
                ToolDefinition(
                    name="set_alert_thresholds",
                    description="Update the CPU, RAM, or disk alert thresholds (percentage).",
                    parameters={
                        "type": "object",
                        "properties": {
                            "cpu_warn":  {"type": "number", "description": "CPU % threshold (e.g. 90)"},
                            "ram_warn":  {"type": "number", "description": "RAM % threshold"},
                            "disk_warn": {"type": "number", "description": "Disk % threshold"},
                        },
                    },
                ),
                self.set_alert_thresholds,
            ),
        ]

    async def get_system_status(self, verbose: bool = False) -> str:
        if not self.enabled:
            return "System monitor unavailable — psutil not installed."
        snap = _take_snapshot(self._cfg)
        return _format_snapshot(snap, verbose=verbose)

    async def set_alert_thresholds(self, cpu_warn: float | None = None,
                                    ram_warn: float | None = None,
                                    disk_warn: float | None = None) -> str:
        changes = []
        if cpu_warn is not None:
            self._cfg.cpu_warn = float(cpu_warn)
            changes.append(f"CPU → {cpu_warn:.0f}%")
        if ram_warn is not None:
            self._cfg.ram_warn = float(ram_warn)
            changes.append(f"RAM → {ram_warn:.0f}%")
        if disk_warn is not None:
            self._cfg.disk_warn = float(disk_warn)
            changes.append(f"Disk → {disk_warn:.0f}%")
        if not changes:
            return "No thresholds changed."
        return "Alert thresholds updated: " + ", ".join(changes)
