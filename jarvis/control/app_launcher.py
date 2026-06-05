import asyncio
import os
import re
import subprocess
import time
from pathlib import Path
from loguru import logger
import psutil

# Recoverable winerror codes from os.startfile — fall through to next strategy.
_RECOVERABLE_WINERRORS = {
    2,     # ERROR_FILE_NOT_FOUND
    1155,  # ERROR_NO_ASSOCIATION
    1223,  # ERROR_CANCELLED (user cancelled UAC or similar)
}

# UWP / Microsoft Store apps that don't have traditional .exe paths.
# Values are AppUserModelId strings for shell:AppsFolder launch.
_UWP_MAP: dict[str, str] = {
    "calculator":  "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
    "calc":        "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",
    "camera":      "Microsoft.WindowsCamera_8wekyb3d8bbwe!App",
    "photos":      "Microsoft.Windows.Photos_8wekyb3d8bbwe!App",
    "settings":    "windows.immersivecontrolpanel",
    "store":       "Microsoft.WindowsStore_8wekyb3d8bbwe!App",
    "mail":        "microsoft.windowscommunicationsapps_8wekyb3d8bbwe!microsoft.windowslive.mail",
    "calendar":    "microsoft.windowscommunicationsapps_8wekyb3d8bbwe!microsoft.windowslive.calendar",
    "maps":        "Microsoft.WindowsMaps_8wekyb3d8bbwe!App",
    "clock":       "Microsoft.WindowsAlarms_8wekyb3d8bbwe!App",
    "alarms":      "Microsoft.WindowsAlarms_8wekyb3d8bbwe!App",
    "weather":     "Microsoft.BingWeather_8wekyb3d8bbwe!App",
    "xbox":        "Microsoft.XboxApp_8wekyb3d8bbwe!Microsoft.XboxApp",
    "snipping tool": "Microsoft.ScreenSketch_8wekyb3d8bbwe!App",
    "sticky notes": "Microsoft.MicrosoftStickyNotes_8wekyb3d8bbwe!App",
    "paint":       "Microsoft.Paint_8wekyb3d8bbwe!App",
    "notepad":     "Microsoft.WindowsNotepad_8wekyb3d8bbwe!App",
}

# How long (seconds) the shortcut cache stays valid before a rebuild.
_CACHE_TTL = 300.0

class AppLauncher:
    def __init__(self):
        self.running_processes = {}
        self._shortcut_cache: dict[str, Path] = {}
        self._cache_time: float = 0.0

    async def launch(self, app_name: str, args: list = None) -> str:
        """
        Launch an application, trying several Windows methods in sequence.

        Order of attempts:
          0. UWP map — for Microsoft Store / built-in apps
          1. os.startfile(app_name) — system commands and full paths
          2. Start Menu shortcut cache — finds installed apps by .lnk name
          3. Shell 'start' command via cmd.exe — last resort; Windows resolves PATH

        Returns a descriptive string (not a raw PID).
        """
        logger.info(f"Launching app: {app_name!r}")

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._launch_sync, app_name, args),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            logger.error(f"Launch timed out for {app_name!r}")
            raise RuntimeError(f"Launching {app_name!r} timed out after 15 seconds")
        except Exception as exc:
            logger.error(f"Failed to launch {app_name!r}: {exc}")
            raise

    def _launch_sync(self, name: str, args: list | None) -> str:
        # 0. UWP / Store apps
        uwp_id = _UWP_MAP.get(name.lower().strip())
        if uwp_id:
            try:
                os.startfile(f"shell:AppsFolder\\{uwp_id}")
                logger.info(f"Launched {name!r} via UWP shell:AppsFolder")
                return f"Launched {name} (UWP app)"
            except Exception as exc:
                logger.debug(f"UWP launch failed for {name!r}: {exc}")

        # 1. Direct startfile (system names, full paths)
        try:
            os.startfile(name)
            logger.info(f"Launched {name!r} via direct startfile")
            return f"Launched {name}"
        except FileNotFoundError:
            pass
        except PermissionError as exc:
            raise RuntimeError(f"Permission denied launching {name!r}: {exc}")
        except OSError as exc:
            winerror = getattr(exc, "winerror", None)
            if winerror in _RECOVERABLE_WINERRORS:
                logger.debug(f"startfile recoverable OSError for {name!r}: {exc}")
            else:
                raise RuntimeError(f"Cannot launch {name!r}: {exc}")

        # 2. Start Menu shortcut cache
        self._ensure_shortcut_cache()
        name_lower = name.lower().strip()
        # Exact match first, then substring
        lnk = self._shortcut_cache.get(name_lower)
        if not lnk:
            for cached_name, cached_path in self._shortcut_cache.items():
                if name_lower in cached_name:
                    lnk = cached_path
                    break
        if lnk:
            logger.info(f"Found shortcut: {lnk}")
            try:
                os.startfile(str(lnk))
                return f"Launched {name} via Start Menu shortcut"
            except Exception as exc:
                logger.warning(f"startfile shortcut failed for {lnk}: {exc}")

        # 3. Shell 'start' command via cmd.exe (no shell=True)
        cmd_args = ["cmd", "/c", "start", "", name]
        if args:
            cmd_args.extend(args)
        logger.info(f"Shell launch: {cmd_args}")
        proc = subprocess.Popen(
            cmd_args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        return f"Launched {name} via shell (PID {proc.pid})"

    def _ensure_shortcut_cache(self) -> None:
        now = time.monotonic()
        if self._shortcut_cache and (now - self._cache_time) < _CACHE_TTL:
            return
        self._shortcut_cache = self._build_shortcut_cache()
        self._cache_time = now
        logger.debug(f"Shortcut cache built: {len(self._shortcut_cache)} entries")

    @staticmethod
    def _build_shortcut_cache() -> dict[str, Path]:
        cache: dict[str, Path] = {}
        search_paths: list[Path] = []
        program_data = os.environ.get("ProgramData", "")
        app_data = os.environ.get("AppData", "")
        if program_data:
            search_paths.append(
                Path(program_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            )
        if app_data:
            search_paths.append(
                Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            )

        for base in search_paths:
            if not base.exists():
                continue
            AppLauncher._scan_dir_for_lnk(base, cache)
        return cache

    @staticmethod
    def _scan_dir_for_lnk(directory: Path, cache: dict[str, Path]) -> None:
        try:
            for entry in os.scandir(directory):
                try:
                    if entry.is_dir(follow_symlinks=False):
                        AppLauncher._scan_dir_for_lnk(Path(entry.path), cache)
                    elif entry.name.lower().endswith(".lnk"):
                        stem = Path(entry.name).stem.lower()
                        if stem not in cache:
                            cache[stem] = Path(entry.path)
                except PermissionError:
                    continue
        except PermissionError:
            pass

    # Common app friendly-name → process name fragment mappings.
    _APP_NAME_MAP: dict[str, str] = {
        "chrome":        "chrome",
        "google chrome": "chrome",
        "firefox":       "firefox",
        "edge":          "msedge",
        "microsoft edge":"msedge",
        "discord":       "discord",
        "spotify":       "spotify",
        "steam":         "steam",
        "obs":           "obs64",
        "notepad":       "notepad",
        "calculator":    "calculatorapp",
        "calc":          "calculatorapp",
        "epic games":    "epicgameslauncher",
        "epic games launcher": "epicgameslauncher",
        "explorer":      "explorer",
        "file explorer": "explorer",
        "opera":         "opera",
        "opera gx":      "opera",
        "vs code":       "code",
        "vscode":        "code",
        "visual studio code": "code",
        "vlc":           "vlc",
        "zoom":          "zoom",
        "teams":         "teams",
        "slack":         "slack",
        "word":          "winword",
        "excel":         "excel",
        "powerpoint":    "powerpnt",
        "outlook":       "outlook",
        "paint":         "mspaint",
        "terminal":      "windowsterminal",
        "cmd":           "cmd",
        "powershell":    "powershell",
        "task manager":  "taskmgr",
    }

    async def close(self, app_name: str) -> bool:
        logger.info(f"Closing: {app_name!r}")
        try:
            if app_name in self.running_processes:
                process = self.running_processes[app_name]
                process.terminate()
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(process.wait), timeout=5.0
                    )
                    del self.running_processes[app_name]
                    logger.info(f"Closed {app_name!r}")
                    return True
                except asyncio.TimeoutError:
                    process.kill()
                    del self.running_processes[app_name]
                    logger.warning(f"Force-killed {app_name!r}")
                    return True

            name_lower = app_name.lower().strip()
            search_fragment = self._APP_NAME_MAP.get(name_lower, name_lower)
            desired = self._normalize_process_name(search_fragment)

            killed: list[str] = []
            for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
                try:
                    proc_name = proc.info["name"] or ""
                    proc_tokens = {
                        self._normalize_process_name(proc_name),
                        self._normalize_process_name(proc.info.get("exe") or ""),
                        self._normalize_process_name(" ".join(proc.info.get("cmdline") or [])),
                    }
                    if any(desired and desired in token for token in proc_tokens):
                        proc.kill()
                        killed.append(proc_name)
                        logger.info(f"Killed {proc_name!r} (pid={proc.info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            if killed:
                logger.info(f"Closed {len(killed)} process(es) for {app_name!r}: {killed[:5]}")
                return True

            # Last resort: taskkill with exact exe name (no wildcards — taskkill
            # doesn't support them in /IM).
            try:
                exe_name = f"{search_fragment}.exe"
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["taskkill", "/F", "/IM", exe_name, "/T"],
                    capture_output=True, text=True, timeout=10,
                )
                output = (result.stdout + result.stderr).strip()
                if result.returncode == 0 or "SUCCESS" in output.upper():
                    logger.info(f"taskkill closed {app_name!r}: {output[:100]}")
                    return True
                logger.debug(f"taskkill no match for {exe_name!r}: {output[:100]}")
            except Exception as exc:
                logger.debug(f"taskkill failed: {exc}")

            logger.warning(f"Process not found: {app_name!r} (searched for {search_fragment!r})")
            return False

        except Exception as exc:
            logger.error(f"Close error for {app_name!r}: {exc}")
            raise

    async def is_running(self, app_name: str) -> bool:
        try:
            if app_name in self.running_processes:
                proc = self.running_processes[app_name]
                if not isinstance(proc, int) and proc.poll() is None:
                    return True
                else:
                    self.running_processes.pop(app_name, None)

            search_name = app_name.lower().strip()
            for proc in psutil.process_iter(["name"]):
                try:
                    if search_name in proc.info["name"].lower():
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return False

        except Exception as exc:
            logger.error(f"is_running check error: {exc}")
            return False

    @staticmethod
    def _normalize_process_name(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", (value or "").lower())

    async def list_running(self) -> list[dict]:
        running = []
        for proc in psutil.process_iter(["pid", "name", "create_time"]):
            try:
                running.append(
                    {
                        "pid":     proc.info["pid"],
                        "name":    proc.info["name"],
                        "created": proc.info["create_time"],
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return running
