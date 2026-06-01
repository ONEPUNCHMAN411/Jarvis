import sys
import os
import argparse

# CUDA DLL bootstrap (MUST run before any ctranslate2 / faster_whisper import)
# When packaged with PyInstaller, NVIDIA CUDA DLLs land in sys._MEIPASS/nvidia/*/bin/.
# ctranslate2 searches os.add_dll_directory() paths for cublas/cudnn at import time,
# so we register those paths here before anything else in the process.
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    _nvidia_base = os.path.join(sys._MEIPASS, 'nvidia')
    if os.path.exists(_nvidia_base):
        for _lib in os.listdir(_nvidia_base):
            _bin = os.path.join(_nvidia_base, _lib, 'bin')
            if os.path.isdir(_bin):
                os.add_dll_directory(_bin)
else:
    # Running from source: add site-packages/nvidia/*/bin to DLL search so
    # ctranslate2 finds cublas64_12.dll / cudnn_ops_infer64_8.dll etc.
    try:
        import importlib.util, pathlib
        _nvidia_spec = importlib.util.find_spec("nvidia")
        if _nvidia_spec and _nvidia_spec.submodule_search_locations:
            for _loc in _nvidia_spec.submodule_search_locations:
                for _sub in pathlib.Path(_loc).iterdir():
                    _bin = _sub / "bin"
                    if _bin.is_dir():
                        os.add_dll_directory(str(_bin))
    except Exception:
        pass

from jarvis.app import main

DEMO_MODE = False

def _install_playwright() -> int:
    """Install Playwright Chromium browser. Called by the NSIS installer post-install."""
    import subprocess
    print("Installing Playwright Chromium browser...")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=False,
    )
    if result.returncode == 0:
        print("Playwright Chromium installed successfully.")
    else:
        print(f"Playwright install failed (exit {result.returncode}).")
    return result.returncode

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JARVIS Desktop AI Assistant")
    parser.add_argument("--demo", action="store_true", help="Enable demo mode (skips voice init, shows auto-demo)")
    parser.add_argument("--minimized", action="store_true", help="Start minimized as floating orb")
    parser.add_argument("--install-playwright", action="store_true", help="Install Playwright Chromium and exit (used by installer)")
    args = parser.parse_args()

    if args.install_playwright:
        sys.exit(_install_playwright())

    if args.demo:
        DEMO_MODE = True
        sys.argv = [arg for arg in sys.argv if arg != "--demo"]

    main(demo_mode=DEMO_MODE)
