"""
Windows startup registration for JARVIS.
Reads/writes HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
"""

import sys

_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "JARVIS"

def _get_exe_path() -> str:
    """Return the path to the running executable."""
    return sys.executable  # PyInstaller sets this to the .exe path

def set_startup(enabled: bool, start_minimized: bool = True) -> bool:
    """
    Add or remove JARVIS from Windows startup.
    Returns True on success, False on failure.
    """
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _REG_KEY,
            0,
            winreg.KEY_SET_VALUE,
        )
        if enabled:
            exe = _get_exe_path()
            args = " --minimized" if start_minimized else ""
            winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, f'"{exe}"{args}')
        else:
            try:
                winreg.DeleteValue(key, _APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False

def is_startup_enabled() -> bool:
    """Return True if JARVIS is registered in Windows startup."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY)
        try:
            winreg.QueryValueEx(key, _APP_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False
