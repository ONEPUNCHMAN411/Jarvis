"""
Manages starting/stopping a llama-server subprocess for JARVIS local inference.

═══════════════════════════════════════════════════════════════
RECOMMENDED SETUP — Vision + Tool Calling (8 GB VRAM)
═══════════════════════════════════════════════════════════════
Target model : Qwen2.5-VL-7B-Instruct-Q4_K_M  (~4.7 GB VRAM)
               → https://huggingface.co/ggml-org/Qwen2.5-VL-7B-Instruct-GGUF
Vision proj  : mmproj-Qwen2.5-VL-7B-Instruct-f16  (~1.1 GB VRAM)
               → same repo (required for screenshot understanding)
Binary       : Standard llama.cpp (Qwen2.5-VL fully supported)
               → https://github.com/ggml-org/llama.cpp

Expected tok/s on RTX 4060 Laptop 8 GB
  Text only  : ~35–50 t/s
  With vision: ~30–45 t/s  (image encoding adds ~500–800 ms TTFT)

VRAM budget  : ~4.7 (model) + 1.1 (mmproj) + 0.6 (KV q4_0) = ~6.4 GB

Text-only alternative (no vision, lower VRAM, better reasoning)
  Qwen3-8B-Q4_K_M (~4.8 GB) — https://huggingface.co/unsloth/Qwen3-8B-GGUF
  DFlash draft via beellama.cpp: https://github.com/Anbeeld/beellama.cpp

═══════════════════════════════════════════════════════════════
KEY FLAGS (researched from benchmarks, GitHub PRs, llama.cpp docs)
═══════════════════════════════════════════════════════════════
-ngl 99              All target layers on GPU (REQUIRED for vision)
--flash-attn         Flash Attention — 1.3-2x faster, less VRAM
--no-mmap            Load full model into RAM upfront, no page faults
--mlock              Pin RAM — prevents OS paging after hours of uptime
-ctk q4_0            KV key cache: 4-bit quantization (2x VRAM saving)
-ctv q4_0            KV val cache: 4-bit quantization
-c 16384             Context window (vision images consume tokens; 16K is safer)
-b 2048 -ub 2048     Larger batch sizes → better throughput
--cont-batching      Continuous batching for concurrent requests
--prio 2             High process scheduling priority
--mmproj <path>      Multimodal projector — enables vision (Qwen2.5-VL)
--host 127.0.0.1    Local only — no network exposure
--log-disable        Suppress noisy logs (JARVIS writes to data/llamacpp.log)
"""

import asyncio
import shutil
import sys
from pathlib import Path

try:
    import httpx as _httpx
except ImportError:
    _httpx = None  # type: ignore

from loguru import logger

DEFAULT_CONFIG = {
    # Model paths
    "model_path": "",           # Required: path to target .gguf
    "mmproj_path": "",          # Multimodal projector for vision (Qwen2.5-VL)
    "draft_model_path": "",     # Speculative decoding draft model (optional)

    # Server network
    "host": "127.0.0.1",
    "port": 8080,

    # GPU offload
    "n_gpu_layers": 99,         # 99 = all layers on GPU
    "n_gpu_layers_draft": 99,

    # Context & batching
    # Vision images consume context tokens. 16K is safer when vision is enabled.
    # Pure text models can use 32K safely.
    "context_size": 16384,
    "parallel": 2,              # 2 concurrent slots
    "batch_size": 2048,
    "ubatch_size": 2048,

    # KV cache quantization
    # Standard llama.cpp: f16, q8_0, q4_0, q4_1, q5_0, q5_1, iq4_nl
    # beellama.cpp extra: turbo4, turbo3, turbo2, turbo4_tcq, turbo3_tcq, turbo2_tcq
    "kv_cache_type_k": "q4_0",
    "kv_cache_type_v": "q4_0",

    # Perf flags
    "flash_attn": True,         # --flash-attn (Ampere+ required)
    "no_mmap": True,            # Load model into RAM — eliminates page faults
    "mlock": True,              # Pin RAM — stability over long uptime
    "cont_batching": True,
    "prio": 2,                  # 0=normal 1=medium 2=high 3=realtime

    # MoE expert pinning (leave 0 for dense models)
    "n_cpu_moe": 0,

    # Extended thinking control (beellama.cpp / Qwen3 only)
    # Set reasoning: "" to disable these flags for non-thinking models.
    # Qwen2.5-VL does NOT use extended thinking — leave these empty.
    "reasoning": "",              # "" = disabled; "off"/"on"/"auto" for Qwen3
    "reasoning_budget": -1,       # -1 = skip flag; 500 for Qwen3 beellama.cpp
    "reasoning_loop_guard": "",   # "" = disabled; "force-close" for Qwen3

    # Speculative decoding
    "spec_type": "",             # "" = disabled
    "spec_draft_n_max": 3,
    "spec_draft_p_min": 0.75,
    "spec_dflash_cross_ctx": 512,

    # NUMA (multi-socket servers only)
    "numa": "",
}

class LlamaCppLauncher:
    """Manages the llama-server subprocess lifecycle for JARVIS."""

    def __init__(self, config: dict):
        self._config = {**DEFAULT_CONFIG, **config}
        self._process: asyncio.subprocess.Process | None = None
        self._log_file: Path | None = None

    # Binary detection

    def _find_llama_server(self) -> str | None:
        """Auto-detect llama-server binary. Prefers beellama.cpp if present."""
        exe = "llama-server.exe" if sys.platform == "win32" else "llama-server"

        # Check PATH first (catches both standard and beellama.cpp installs)
        if found := shutil.which(exe):
            return found

        candidates: list[Path] = []
        if sys.platform == "win32":
            candidates += [
                Path(r"C:\llama.cpp") / exe,
                Path(r"C:\beellama.cpp") / exe,
                Path(r"C:\Program Files\llama.cpp") / exe,
                Path.home() / "llama.cpp" / exe,
                Path.home() / "beellama.cpp" / exe,
            ]
        candidates += [
            Path.home() / ".local" / "bin" / exe,
            Path("/opt/homebrew/bin") / exe,
            Path("/usr/local/bin") / exe,
        ]

        for p in candidates:
            if p.exists():
                return str(p)

        return None

    # Command construction — ALL researched flags

    def _build_command(self) -> list[str]:
        c = self._config
        binary = self._find_llama_server()
        if not binary:
            raise RuntimeError(
                "llama-server not found.\n"
                "Install llama.cpp: https://github.com/ggml-org/llama.cpp\n"
                "Or beellama.cpp (Qwen3 DFlash): https://github.com/Anbeeld/beellama.cpp"
            )

        cmd: list[str] = [binary]

        # Model
        cmd += ["--model", c["model_path"]]

        # Multimodal projector (vision)
        if c.get("mmproj_path"):
            cmd += ["--mmproj", c["mmproj_path"]]

        # GPU offload
        if c["n_gpu_layers"] > 0:
            cmd += ["-ngl", str(c["n_gpu_layers"])]

        # Draft model + GPU offload for drafter
        if c.get("draft_model_path"):
            cmd += ["-md", c["draft_model_path"]]
            if c["n_gpu_layers_draft"] > 0:
                cmd += ["-ngld", str(c["n_gpu_layers_draft"])]

        # Flash attention
        if c["flash_attn"]:
            cmd += ["--flash-attn", "on"]   # beellama.cpp requires explicit "on"

        # RAM management
        if c["no_mmap"]:
            cmd.append("--no-mmap")
        if c["mlock"]:
            cmd.append("--mlock")

        # KV cache quantization
        if c["kv_cache_type_k"]:
            cmd += ["-ctk", c["kv_cache_type_k"]]
        if c["kv_cache_type_v"]:
            cmd += ["-ctv", c["kv_cache_type_v"]]

        # Context & batch
        cmd += ["-c", str(c["context_size"])]
        cmd += ["-b", str(c["batch_size"]), "-ub", str(c["ubatch_size"])]

        # Parallel slots
        par = c.get("parallel", 2)
        if par > 1:
            cmd += ["--parallel", str(par)]

        # Continuous batching
        if c["cont_batching"]:
            cmd.append("--cont-batching")

        # Process priority
        if c["prio"] > 0:
            cmd += ["--prio", str(c["prio"])]

        # MoE expert pinning
        if c["n_cpu_moe"] > 0:
            cmd += ["--n-cpu-moe", str(c["n_cpu_moe"])]

        # Qwen3 / beellama.cpp thinking control
        # Only applies when reasoning is explicitly set ("off"/"on"/"auto").
        # Leave reasoning: "" for Qwen2.5-VL and other non-thinking models.
        if c.get("reasoning") in ("off", "on", "auto"):
            cmd += ["--reasoning", c["reasoning"]]
        reasoning_budget = c.get("reasoning_budget", -1)
        if reasoning_budget != -1:          # -1 = default unlimited (skip flag)
            cmd += ["--reasoning-budget", str(reasoning_budget)]
        if c.get("reasoning_loop_guard") in ("force-close", "stop"):
            cmd += ["--reasoning-loop-guard", c["reasoning_loop_guard"]]

        # Speculative decoding
        spec = c.get("spec_type", "")
        if spec:
            cmd += ["--spec-type", spec]
            cmd += ["--spec-draft-n-max", str(c["spec_draft_n_max"])]
            cmd += ["--spec-draft-p-min", str(c["spec_draft_p_min"])]
            if spec == "dflash":
                cmd += ["--spec-dflash-cross-ctx", str(c["spec_dflash_cross_ctx"])]

        # NUMA (multi-socket CPUs only)
        if c.get("numa"):
            cmd += ["--numa", c["numa"]]

        # Network
        cmd += ["--host", c["host"]]
        cmd += ["--port", str(c["port"])]
        cmd.append("--log-disable")

        return cmd

    # Lifecycle

    async def start(self) -> bool:
        """Start llama-server. Returns True if started or already running."""
        if await self.is_running():
            logger.info("llama-server already running — skipping launch")
            return True

        if not self._config.get("model_path"):
            logger.error("llamacpp: model_path not set — cannot start server")
            return False

        try:
            log_dir = Path("data")
            log_dir.mkdir(exist_ok=True)
            self._log_file = log_dir / "llamacpp.log"

            cmd = self._build_command()
            logger.info("Starting llama-server:\n  {}", " \\\n  ".join(cmd))

            with open(self._log_file, "ab") as log_f:
                self._process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=log_f,
                    stderr=asyncio.subprocess.STDOUT,
                )
            logger.info("llama-server PID {}", self._process.pid)

            ready = await self.wait_until_ready(timeout=120.0)
            if not ready:
                logger.error("llama-server not ready after 120s — see data/llamacpp.log")
                await self.stop()
                return False

            await self._prewarm()
            logger.info("llama-server ready ✓")
            return True

        except Exception as e:
            logger.error("Failed to start llama-server: {}", e)
            return False

    async def stop(self) -> None:
        """Terminate llama-server gracefully, force-kill if needed."""
        if not self._process:
            return
        try:
            logger.info("Stopping llama-server")
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Force-killing llama-server")
                self._process.kill()
                await self._process.wait()
        except Exception as e:
            logger.error("Error stopping llama-server: {}", e)
        finally:
            self._process = None

    async def is_running(self) -> bool:
        """Check /health — works even for externally started servers."""
        if _httpx is None:
            return False
        try:
            async with _httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(
                    f"http://{self._config['host']}:{self._config['port']}/health"
                )
                return r.status_code == 200
        except Exception:
            return False

    async def wait_until_ready(self, timeout: float = 120.0) -> bool:
        """Poll /health every 500 ms until ready or timeout."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            if await self.is_running():
                return True
            await asyncio.sleep(0.5)
        logger.warning("llama-server not ready after {}s", timeout)
        return False

    async def _prewarm(self) -> None:
        """Fire a dummy request to load weights into VRAM before first real query."""
        if _httpx is None:
            return
        try:
            async with _httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(
                    f"http://{self._config['host']}:{self._config['port']}/v1/completions",
                    json={"prompt": " ", "max_tokens": 1},
                )
                if r.status_code == 200:
                    logger.debug("llama-server pre-warm done")
        except Exception as e:
            logger.warning("llama-server pre-warm failed (non-fatal): {}", e)
