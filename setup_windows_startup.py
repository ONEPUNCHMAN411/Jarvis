#!/usr/bin/env python
"""
Setup JARVIS to start automatically on Windows power on.
Run with: python setup_windows_startup.py
"""

import sys
import os
import subprocess
from pathlib import Path
from loguru import logger

logger.info("Setting up JARVIS Windows Startup...")


def setup_startup_registry():
    """Add JARVIS to Windows startup via Registry (Run key)."""
    try:
        import winreg

        jarvis_dir = Path(__file__).parent
        python_exe = sys.executable
        jarvis_script = jarvis_dir / "jarvis" / "__main__.py"

        cmd = f'"{python_exe}" -m jarvis'

        logger.info(f"Registry command: {cmd}")
        logger.info(f"Working directory: {jarvis_dir}")

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "JARVIS", 0, winreg.REG_SZ, cmd)
            winreg.CloseKey(key)

            logger.info("✓ JARVIS registered in Windows startup (Registry)")
            return True
        except Exception as e:
            logger.error(f"Failed to set registry: {e}")
            return False

    except ImportError:
        logger.error("winreg module not available (Windows only)")
        return False


def setup_startup_shortcut():
    """Add JARVIS to Windows startup folder via shortcut."""
    try:
        import win32com.client
        from pathlib import Path

        startup_folder = Path.home() / "AppData\\Roaming\\Microsoft\\Windows\\Start Menu\\Programs\\Startup"

        if not startup_folder.exists():
            logger.error(f"Startup folder not found: {startup_folder}")
            return False

        jarvis_dir = Path(__file__).parent
        python_exe = sys.executable

        shortcut_path = startup_folder / "JARVIS.lnk"

        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(shortcut_path))
        shortcut.TargetPath = python_exe
        shortcut.Arguments = "-m jarvis"
        shortcut.WorkingDirectory = str(jarvis_dir)
        shortcut.IconLocation = str(jarvis_dir / "jarvis.ico") if (jarvis_dir / "jarvis.ico").exists() else ""
        shortcut.Description = "JARVIS - AI Personal Assistant"
        shortcut.save()

        logger.info(f"✓ JARVIS shortcut created in startup folder: {shortcut_path}")
        return True

    except ImportError:
        logger.warning("pywin32 not installed, trying registry method instead")
        return False
    except Exception as e:
        logger.error(f"Failed to create startup shortcut: {e}")
        return False


def setup_scheduled_task():
    """Add JARVIS to Windows Task Scheduler."""
    try:
        jarvis_dir = Path(__file__).parent
        python_exe = sys.executable

        cmd = f"""
        schtasks /create /tn "JARVIS Startup" /tr "'{python_exe}' -m jarvis" /sc onlogon /rl highest /f
        """

        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if result.returncode == 0:
            logger.info("✓ JARVIS registered in Windows Task Scheduler")
            return True
        else:
            logger.warning(f"Task Scheduler setup had issues: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"Failed to setup Task Scheduler: {e}")
        return False


def verify_startup():
    """Verify JARVIS is registered for startup."""
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)

        try:
            value, _ = winreg.QueryValueEx(key, "JARVIS")
            logger.info(f"✓ JARVIS startup verified: {value}")
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            logger.warning("JARVIS not found in startup registry")
            winreg.CloseKey(key)
            return False

    except Exception as e:
        logger.error(f"Failed to verify startup: {e}")
        return False


def main():
    print("\n" + "="*60)
    print("JARVIS Windows Startup Setup")
    print("="*60 + "\n")

    print("This will configure JARVIS to start automatically when Windows boots.\n")

    choice = input("Setup startup method:\n1. Registry (recommended)\n2. Startup Folder\n3. Task Scheduler\nChoice (1-3): ").strip()

    success = False

    if choice == "1":
        success = setup_startup_registry()
    elif choice == "2":
        success = setup_startup_shortcut()
    elif choice == "3":
        success = setup_scheduled_task()
    else:
        print("Invalid choice")
        return

    if success:
        print("\n✓ Startup setup successful!")
        verify_startup()
        print("\nJARVIS will now start automatically on the next Windows boot.")
        print("To disable: Remove 'JARVIS' from Windows startup settings.")
    else:
        print("\n✗ Startup setup failed. Try running as Administrator.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Setup cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Setup error: {e}")
        sys.exit(1)
