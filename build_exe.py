#!/usr/bin/env python
"""
Build JARVIS as a standalone executable using PyInstaller.

Run from the jarvis directory:
    python build_exe.py             # build EXE only
    python build_exe.py --installer # build EXE then compile NSIS installer

Output:
    dist/JARVIS/JARVIS.exe          PyInstaller folder build (for installer)
    installer/JARVIS-Setup-*.exe    (with --installer flag, requires NSIS)
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

VERSION = "1"


def _ensure_cuda_packages() -> bool:
    """Always install nvidia CUDA packages so PyInstaller can bundle the DLLs.
    They are only ~300 MB and only load at runtime when a GPU is present.
    Skipping them means EXE users with GPUs get CPU-only voice — not acceptable."""

    # Quick NVIDIA GPU check via wmic (doesn't require torch)
    gpu_name = "unknown GPU"
    try:
        r = subprocess.run(
            ["wmic", "path", "win32_VideoController", "get", "name", "/value"],
            capture_output=True, text=True, timeout=5,
        )
        for line in r.stdout.splitlines():
            if "NVIDIA" in line:
                gpu_name = line.split("=", 1)[-1].strip()
                break
        else:
            # No NVIDIA GPU line found — still install packages; harmless on CPU
            print("[*] No NVIDIA GPU detected via wmic — installing CUDA packages anyway (harmless on CPU)")
    except Exception:
        print("[*] GPU detection skipped — installing CUDA packages anyway")

    if "NVIDIA" in gpu_name:
        print(f"[*] GPU detected: {gpu_name} — installing CUDA packages for voice acceleration...")

    cuda_pkgs = ["nvidia-cublas-cu12", "nvidia-cudnn-cu12",
                 "nvidia-cuda-runtime-cu12", "nvidia-curand-cu12"]
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", *cuda_pkgs],
        capture_output=False,
    )
    if result.returncode == 0:
        print("[OK] CUDA packages installed — GPU voice DLLs will be bundled into EXE")
        return True
    else:
        print("[WARN] CUDA package install failed — EXE will use CPU voice")
        return False


def build_exe():
    print(f"[*] Building JARVIS v{VERSION} ...")
    print()

    jarvis_dir = Path(__file__).parent
    dist_dir   = jarvis_dir / "dist"
    build_dir  = jarvis_dir / "build"

    # Kill any running JARVIS.exe so it doesn't lock the dist folder
    try:
        subprocess.run(
            ["taskkill", "/f", "/im", "JARVIS.exe"],
            capture_output=True,
        )
    except Exception:
        pass

    # Ensure CUDA packages are installed so PyInstaller can bundle CUDA DLLs
    _ensure_cuda_packages()

    # Clean previous output
    print("[*] Cleaning up old releases...")
    for p in [dist_dir, build_dir]:
        if p.exists():
            try:
                shutil.rmtree(p)
            except Exception as e:
                print(f"    [WARN] Could not remove {p}: {e}")

    print("[*] Running PyInstaller...")

    # Use --onedir for installer builds so NSIS can reference the folder.
    # Still produces a single logical "app" from the user's perspective via the installer.
    build_mode = "--onedir" if "--installer" in sys.argv else "--onefile"

    # Icon path — fall back gracefully if missing
    icon_path = jarvis_dir / "assets" / "jarvis.ico"
    icon_args = ["--icon", str(icon_path)] if icon_path.exists() else []

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=JARVIS",
        build_mode,
        "--noconfirm",
        "--noconsole",
        f"--distpath={dist_dir}",
        f"--workpath={build_dir}",
        *icon_args,

        # Data files
        "--add-data", f"{jarvis_dir / 'config'}:config",
        "--add-data", f"{jarvis_dir / 'jarvis' / 'ui' / 'assets'}:jarvis/ui/assets",

        # Large binary packages — collect binaries + data
        "--collect-all=aiohttp",
        "--collect-all=ctranslate2",
        "--collect-all=faster_whisper",
        "--collect-all=openwakeword",
        "--collect-all=onnxruntime",
        "--collect-all=playwright",

        # silero-vad ONNX model file (runs via onnxruntime, torch not required)
        "--collect-data=silero_vad",

        # tqdm metadata (required by huggingface_hub / faster_whisper download)
        "--copy-metadata=tqdm",

        # accelerate metadata (required by transformers version check)
        "--copy-metadata=accelerate",

        # NOTE: CUDA DLLs (nvidia.cublas/cudnn/cuda_runtime/curand) are NOT bundled.
        # ctranslate2 loads them from the user's CUDA/cuDNN installation at runtime.
        # Bundling them adds 3+ GB and breaks the 2 GB GitHub release file limit.
        # GPU acceleration works on any machine with CUDA 12 drivers installed.

        # Exclusions — crash-prone or not used by JARVIS
        "--exclude-module=antigravity",
        "--exclude-module=turtle",
        "--exclude-module=tkinter",
        "--exclude-module=test",
        # grpc native DLLs cause STATUS_STACK_BUFFER_OVERRUN on startup.
        # google.generativeai uses REST, not gRPC — safe to exclude.
        "--exclude-module=grpc",
        "--exclude-module=grpcio",
        # Large torch transitive deps not used by JARVIS — excluding these
        # keeps the bundle under PyInstaller's 4 GB CArchive limit.
        "--exclude-module=scipy",
        "--exclude-module=pandas",
        "--exclude-module=matplotlib",
        "--exclude-module=sklearn",
        "--exclude-module=sympy",
        "--exclude-module=gradio",
        "--exclude-module=torchaudio",
        "--exclude-module=torchvision",
        "--exclude-module=pyarrow",
        "--exclude-module=datasets",
        "--exclude-module=bitsandbytes",
        "--exclude-module=tensorflow",
        "--exclude-module=jax",
        "--exclude-module=cv2",
        "--exclude-module=IPython",
        "--exclude-module=notebook",
        "--exclude-module=jupyterlab",
        # torch is not needed at runtime — faster-whisper uses ctranslate2,
        # silero-vad loads via onnxruntime. Excluding saves ~3 GB from the bundle.
        "--exclude-module=torch",
        "--exclude-module=torchaudio",
        "--exclude-module=torchvision",

        # ── Hidden imports ────────────────────────────────────────────────
        "--hidden-import=aiohttp",
        "--hidden-import=aiohttp.web",
        "--hidden-import=jarvis.api.local_server",
        "--hidden-import=cryptography.fernet",
        "--hidden-import=cryptography.hazmat.primitives.kdf.pbkdf2",
        "--hidden-import=aiosqlite",
        "--hidden-import=edge_tts",
        "--hidden-import=faster_whisper",
        "--hidden-import=loguru",
        "--hidden-import=jarvis.brain.mistral_provider",
        "--hidden-import=jarvis.brain.claude_provider",
        "--hidden-import=jarvis.brain.claude_code_provider",
        "--hidden-import=jarvis.brain.openai_provider",
        "--hidden-import=jarvis.ui.setup_wizard",
        "--hidden-import=jarvis.utils.first_run",
        "--hidden-import=httpx",
        "--hidden-import=mss",
        "--hidden-import=numpy",
        "--hidden-import=onnxruntime",
        "--hidden-import=PIL",
        "--hidden-import=playwright.async_api",
        "--hidden-import=psutil",
        "--hidden-import=pyautogui",
        "--hidden-import=pynput",
        "--hidden-import=pynput.keyboard",
        "--hidden-import=pynput.mouse",
        "--hidden-import=jarvis.utils.hotkey",
        "--hidden-import=pyperclip",
        "--hidden-import=encodings",
        "--hidden-import=encodings.utf_8",
        "--hidden-import=PyQt6.QtCore",
        "--hidden-import=PyQt6.QtGui",
        "--hidden-import=PyQt6.QtWidgets",
        "--hidden-import=silero_vad",
        "--hidden-import=sounddevice",
        "--hidden-import=soundfile",
        "--hidden-import=torch",
        "--hidden-import=jarvis.brain.ai_summarizer",
        "--hidden-import=jarvis.brain.code_executor",
        "--hidden-import=jarvis.brain.image_utils",
        "--hidden-import=jarvis.brain.llamacpp_provider",
        "--hidden-import=jarvis.brain.workflow_engine",
        "--hidden-import=jarvis.control.screen_reader",
        "--hidden-import=jarvis.plugins.scheduler_plugin",
        "--hidden-import=jarvis.ui.ollama_manager",
        "--hidden-import=jarvis.utils.llamacpp_launcher",
        "--hidden-import=jarvis.utils.llamacpp_benchmark",
        "--hidden-import=google.oauth2.credentials",
        "--hidden-import=google.auth.transport.requests",
        "--hidden-import=jarvis.voice.desktop_audio",
        "--collect-all=pyaudiowpatch",

        str(jarvis_dir / "jarvis" / "__main__.py"),
    ]

    try:
        result = subprocess.run(cmd, cwd=str(jarvis_dir), capture_output=False)

        if result.returncode == 0:
            if "--installer" in sys.argv:
                exe_path = dist_dir / "JARVIS" / "JARVIS.exe"
            else:
                exe_path = dist_dir / "JARVIS.exe"
            print()
            print(f"[OK] JARVIS v{VERSION} build complete!")
            print(f"[OK] Location: {exe_path}")
            print()
            if "--installer" in sys.argv:
                return build_installer(jarvis_dir)
            else:
                print("Double-click dist\\JARVIS.exe to launch")
                _install_playwright(dist_dir / "JARVIS.exe" if (dist_dir / "JARVIS.exe").exists() else None)
            return True
        else:
            print(f"\n[FAIL] Build failed (return code {result.returncode})")
            return False

    except Exception as e:
        print(f"[FAIL] Error during build: {e}")
        return False


def _install_playwright(exe_path) -> None:
    """Install Playwright Chromium browser so JARVIS can automate the web out of the box."""
    print("[*] Installing Playwright Chromium browser (required for web automation)...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=False, timeout=300,
        )
        if result.returncode == 0:
            print("[OK] Playwright Chromium installed")
        else:
            print("[WARN] Playwright install returned non-zero — web automation may not work")
    except Exception as e:
        print(f"[WARN] Playwright install skipped: {e}")


def build_installer(jarvis_dir: Path) -> bool:
    """Compile the Inno Setup script into a setup EXE."""
    iss_script = jarvis_dir / "installer" / "jarvis_setup.iss"
    if not iss_script.exists():
        print("[FAIL] installer/jarvis_setup.iss not found — skipping installer build")
        return False

    iscc = shutil.which("iscc")
    if not iscc:
        import os as _os
        for candidate in [
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            r"C:\Program Files\Inno Setup 6\ISCC.exe",
            _os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
        ]:
            if os.path.exists(candidate):
                iscc = candidate
                break
    if not iscc:
        print("[WARN] ISCC.exe not found — install Inno Setup: winget install JRSoftware.InnoSetup")
        print("[WARN] Skipping installer build (dist\\JARVIS\\ folder is still usable)")
        return True

    print("[*] Building Inno Setup installer...")
    result = subprocess.run(
        [iscc, str(iss_script)],
        cwd=str(jarvis_dir / "installer"),
    )
    if result.returncode == 0:
        installer_path = jarvis_dir / "installer" / f"JARVIS-Setup-v{VERSION}.exe"
        print(f"[OK] Installer: {installer_path}")
        return True
    else:
        print(f"[FAIL] Inno Setup build failed (return code {result.returncode})")
        return False


if __name__ == "__main__":
    print(f"  --installer   also build NSIS setup wizard installer" if "--help" in sys.argv else "")
    try:
        success = build_exe()
        if success:
            print()
            if "--installer" in sys.argv:
                print(f"Build complete — distribute installer\\JARVIS-Setup-v{VERSION}.exe")
            else:
                print("Build complete — double-click dist\\JARVIS.exe to launch.")
        else:
            print()
            print("Build failed. Check the errors above.")
            sys.exit(1)
    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}")
        sys.exit(1)
