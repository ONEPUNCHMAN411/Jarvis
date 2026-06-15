"""
JARVIS Code Executor — safe sandboxed code execution for Python, shell, and JavaScript.
"""
import asyncio
import subprocess
import sys
import tempfile
import os
import time
from loguru import logger

class CodeExecutor:
    """Execute code snippets safely with timeout and output capture."""

    TIMEOUT_S = 15  # max execution time
    MAX_OUTPUT = 4000  # max chars of output

    async def run_python(self, code: str, timeout: int = 15) -> dict:
        """
        Execute Python code in a subprocess.
        Returns: {"success": bool, "output": str, "error": str, "runtime_ms": int}
        """
        timeout = max(1, min(int(timeout), self.TIMEOUT_S))
        start_time = time.time()

        try:
            # Write to temp file for multi-line code support
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(code)
                temp_file = f.name

            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    # --isolated: skip PYTHONSTARTUP, user site-packages, and PYTHON* env vars
                    [sys.executable, "-I", temp_file],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

                runtime_ms = int((time.time() - start_time) * 1000)
                output = (result.stdout + result.stderr).strip()

                if result.returncode == 0:
                    return {
                        "success": True,
                        "output": output[:self.MAX_OUTPUT] if output else "(no output)",
                        "error": "",
                        "runtime_ms": runtime_ms,
                        "language": "python",
                    }
                else:
                    return {
                        "success": False,
                        "output": output[:self.MAX_OUTPUT] if output else "",
                        "error": result.stderr.strip() or "Exit code: " + str(result.returncode),
                        "runtime_ms": runtime_ms,
                        "language": "python",
                    }
            finally:
                try:
                    os.unlink(temp_file)
                except Exception:
                    pass

        except subprocess.TimeoutExpired as exc:
            runtime_ms = int((time.time() - start_time) * 1000)
            # Kill entire process tree so child processes can't outlive the timeout
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(exc.cmd)],
                    capture_output=True, timeout=5,
                )
            except Exception:
                pass
            return {
                "success": False,
                "output": "",
                "error": f"Execution timeout after {timeout} seconds",
                "runtime_ms": runtime_ms,
                "language": "python",
            }
        except Exception as e:
            runtime_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Python execution error: {e}")
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "runtime_ms": runtime_ms,
                "language": "python",
            }

    async def run_shell(self, command: str, timeout: int = 30) -> dict:
        """Run a shell command, return {success, output, error, runtime_ms}."""
        timeout = max(1, min(int(timeout), 120))
        start_time = time.time()

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            runtime_ms = int((time.time() - start_time) * 1000)
            output = (result.stdout + result.stderr).strip()

            if result.returncode == 0:
                return {
                    "success": True,
                    "output": output[:self.MAX_OUTPUT] if output else "(no output)",
                    "error": "",
                    "runtime_ms": runtime_ms,
                    "language": "shell",
                }
            else:
                return {
                    "success": False,
                    "output": output[:self.MAX_OUTPUT] if output else "",
                    "error": result.stderr.strip() or "Exit code: " + str(result.returncode),
                    "runtime_ms": runtime_ms,
                    "language": "shell",
                }
        except subprocess.TimeoutExpired:
            runtime_ms = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "output": "",
                "error": f"Command timeout after {timeout} seconds",
                "runtime_ms": runtime_ms,
                "language": "shell",
            }
        except Exception as e:
            runtime_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Shell execution error: {e}")
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "runtime_ms": runtime_ms,
                "language": "shell",
            }

    async def run_javascript(self, code: str, timeout: int = 10) -> dict:
        """
        Run JavaScript via Node.js if available.
        Returns {success, output, error, runtime_ms}.
        Falls back gracefully if node not found.
        """
        timeout = max(1, min(int(timeout), 60))
        start_time = time.time()

        try:
            # Check if Node.js is available
            check_result = await asyncio.to_thread(
                subprocess.run,
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=2,
            )

            if check_result.returncode != 0:
                runtime_ms = int((time.time() - start_time) * 1000)
                return {
                    "success": False,
                    "output": "",
                    "error": "Node.js is not installed or not in PATH",
                    "runtime_ms": runtime_ms,
                    "language": "javascript",
                }

            # Write to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8') as f:
                f.write(code)
                temp_file = f.name

            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["node", temp_file],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

                runtime_ms = int((time.time() - start_time) * 1000)
                output = (result.stdout + result.stderr).strip()

                if result.returncode == 0:
                    return {
                        "success": True,
                        "output": output[:self.MAX_OUTPUT] if output else "(no output)",
                        "error": "",
                        "runtime_ms": runtime_ms,
                        "language": "javascript",
                    }
                else:
                    return {
                        "success": False,
                        "output": output[:self.MAX_OUTPUT] if output else "",
                        "error": result.stderr.strip() or "Exit code: " + str(result.returncode),
                        "runtime_ms": runtime_ms,
                        "language": "javascript",
                    }
            finally:
                try:
                    os.unlink(temp_file)
                except Exception:
                    pass

        except subprocess.TimeoutExpired:
            runtime_ms = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "output": "",
                "error": f"Execution timeout after {timeout} seconds",
                "runtime_ms": runtime_ms,
                "language": "javascript",
            }
        except Exception as e:
            runtime_ms = int((time.time() - start_time) * 1000)
            logger.error(f"JavaScript execution error: {e}")
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "runtime_ms": runtime_ms,
                "language": "javascript",
            }

    async def run_python_with_packages(self, code: str, timeout: int = 15) -> dict:
        """
        Execute Python code, but first check if all imported packages are installed.
        Returns a warning dict if any imports are missing (does not auto-install).
        Returns {success, output, error, runtime_ms, language, missing_packages}.
        """
        import re

        # Parse top-level import statements for package names
        import_pattern = re.compile(
            r"^\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE
        )
        imported_names = set(import_pattern.findall(code))

        # Stdlib modules to exclude from the missing-package check
        stdlib_modules = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else set()

        missing: list[str] = []
        for name in imported_names:
            if name in stdlib_modules:
                continue
            try:
                __import__(name)
            except ImportError:
                missing.append(name)

        if missing:
            return {
                "success": False,
                "output": "",
                "error": (
                    f"Missing packages: {', '.join(sorted(missing))}. "
                    "Install them with: pip install " + " ".join(sorted(missing))
                ),
                "runtime_ms": 0,
                "language": "python",
                "missing_packages": missing,
            }

        result = await self.run_python(code, timeout=timeout)
        result["missing_packages"] = []
        return result

    def format_result(self, result: dict, language: str = "") -> str:
        """Format execution result as a readable string for JARVIS response."""
        runtime = result.get("runtime_ms", 0)
        if result["success"]:
            out = result["output"].strip() or "(no output)"
            return f"✅ Executed in {runtime}ms:\n{out}"
        else:
            err = result["error"].strip() or result["output"].strip()
            return f"❌ Error ({runtime}ms):\n{err}"
