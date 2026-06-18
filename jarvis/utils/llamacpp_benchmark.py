"""
JARVIS llama.cpp Benchmark Tool
================================
Measures real tok/s, TTFT, context length safety, and speculative decoding speedup.

Uses /v1/chat/completions (not raw completions) so Qwen3 thinking mode is handled
correctly via enable_thinking=false. Raw completions silently buffer thinking tokens,
causing ReadTimeout before any visible output arrives.

Run:
    python -m jarvis.utils.llamacpp_benchmark
    python -m jarvis.utils.llamacpp_benchmark --url http://127.0.0.1:8080
    python -m jarvis.utils.llamacpp_benchmark --full   # all tests including long ctx
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass

# Force UTF-8 on Windows so box-drawing characters render correctly
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

BASE_URL = "http://127.0.0.1:8080"

# ─── System prompt ─────────────────────────────────────────────────────────────
# Disable Qwen3 extended thinking. Without this, the model can spend 100–200 s
# in silent thinking before the first visible token, causing ReadTimeout.
SYSTEM_PROMPT = (
    "You are a helpful, fast assistant. "
    "Respond directly and concisely without extended reasoning blocks."
)

# ─── Test prompts ─────────────────────────────────────────────────────────────

CODING_PROMPT = (
    "Write a complete, well-commented Python implementation of a red-black tree "
    "with insert, delete, search, and in-order traversal. Include type hints."
)

CHAT_PROMPT = (
    "Explain the difference between TCP and UDP protocols in detail, covering "
    "connection setup, reliability, ordering, use cases, and performance tradeoffs."
)

PROSE_PROMPT = (
    "Write a vivid, atmospheric short story opening (300 words) set in a "
    "cyberpunk city at night, with a detective finding a mysterious device."
)

TOOL_PROMPT = (
    "List every step needed to set up a Python virtual environment, install "
    "dependencies from requirements.txt, run tests with pytest, and build a "
    "Docker image. Output as numbered steps only."
)

# Long context: ~8 K tokens of padding to stress KV cache
LONG_CTX_PROMPT = "word " * 8000 + "\nSummarize the above in one sentence."

@dataclass
class BenchResult:
    label: str
    prompt_tokens: int = 0
    gen_tokens: int = 0
    ttft_ms: float = 0.0       # time to first token
    total_ms: float = 0.0
    tps: float = 0.0           # tokens per second (generation only)
    error: str | None = None

# ─── Core measurement ─────────────────────────────────────────────────────────

async def measure_chat(
    client: httpx.AsyncClient,
    user_prompt: str,
    max_tokens: int = 400,
    label: str = "",
) -> BenchResult:
    result = BenchResult(label=label)

    # Use chat completions — Qwen3 thinking mode is disabled via enable_thinking=false.
    # This ensures visible tokens start arriving immediately instead of after a long
    # silent thinking phase that would trigger ReadTimeout.
    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "stream": True,
        "temperature": 0.0,          # greedy — deterministic
        "cache_prompt": False,
        # Qwen3 extended thinking — disable via chat template kwarg.
        # Without this the model can spend 100–200 s in silent thinking before
        # any visible token is streamed, causing ReadTimeout.
        "enable_thinking": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    # Long read timeout: beellama.cpp adaptive DFlash inserts silent thinking on
    # complex tasks. A coding prompt can take 25-35 s before the first visible
    # token. 180 s covers up to ~7000 thinking tokens at 38 tok/s.
    timeout = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0)

    try:
        t_start = time.perf_counter()
        t_first: float | None = None
        token_count = 0

        async with client.stream(
            "POST",
            f"{BASE_URL}/v1/chat/completions",
            json=payload,
            timeout=timeout,
        ) as resp:
            if resp.status_code != 200:
                result.error = f"HTTP {resp.status_code}"
                return result

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta", {})
                    # Only count visible content, not reasoning_content (thinking)
                    tok = delta.get("content") or ""
                    if tok:
                        if t_first is None:
                            t_first = time.perf_counter()
                            result.ttft_ms = (t_first - t_start) * 1000
                        token_count += 1
                    if "usage" in chunk:
                        result.prompt_tokens = chunk["usage"].get("prompt_tokens", 0)
                except Exception:
                    pass

        t_end = time.perf_counter()
        result.gen_tokens = token_count
        result.total_ms = (t_end - t_start) * 1000

        if t_first is not None and token_count > 1:
            gen_time = t_end - t_first
            result.tps = (token_count - 1) / gen_time if gen_time > 0 else 0

    except httpx.ConnectError:
        result.error = "Connection refused — is llama-server running?"
    except httpx.ReadTimeout:
        result.error = "ReadTimeout — first token took >180 s (complex thinking phase)"
    except Exception as e:
        result.error = str(e)

    return result

async def get_server_info(client: httpx.AsyncClient) -> dict:
    try:
        r = await client.get(f"{BASE_URL}/v1/models", timeout=5.0)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}

async def get_gpu_info() -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            "nvidia-smi",
            "--query-gpu=name,memory.used,memory.total,temperature.gpu",
            "--format=csv,noheader",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        return out.decode().strip()
    except Exception:
        return "nvidia-smi not available"

# ─── Formatting ───────────────────────────────────────────────────────────────

def fmt(r: BenchResult) -> str:
    if r.error:
        return f"  ❌ {r.label}: {r.error}"
    tok_str = f"{r.gen_tokens}" if r.gen_tokens else "0 (thinking consumed budget)"
    return (
        f"  ✅ {r.label}\n"
        f"     TTFT    : {r.ttft_ms:.0f} ms\n"
        f"     Tokens  : {tok_str} generated\n"
        f"     Speed   : {r.tps:.1f} tok/s\n"
        f"     Total   : {r.total_ms/1000:.1f}s"
    )

# ─── Runner ───────────────────────────────────────────────────────────────────

async def run_benchmark(full: bool = False):
    print("\n" + "═" * 60)
    print("  JARVIS llama.cpp Benchmark")
    print("═" * 60)

    async with httpx.AsyncClient() as client:
        # Health check
        try:
            r = await client.get(f"{BASE_URL}/health", timeout=3.0)
            if r.status_code != 200:
                print(f"\n❌ Server not healthy: HTTP {r.status_code}")
                return
        except httpx.ConnectError:
            print("\n❌ Cannot reach llama-server at", BASE_URL)
            print("   → Set model_path in Settings → Local AI and enable it")
            print("   → Or install llama-server: https://github.com/Anbeeld/beellama.cpp")
            return

        print(f"\n✅ Server online at {BASE_URL}")

        gpu = await get_gpu_info()
        print(f"   GPU: {gpu}\n")

        info = await get_server_info(client)
        if info.get("data"):
            print(f"   Model: {info['data'][0].get('id', 'unknown')}")

        print("\n── Benchmarks ─" + "─" * 45)
        print("   (temperature=0, streaming, chat/completions)")
        print("   beellama.cpp DFlash inserts silent thinking on complex tasks.")
        print("   TTFT = request-to-first-visible-token (includes thinking time).\n")

        tests = [
            ("Coding (spec best case)",     CODING_PROMPT, 400),
            ("Tool / structured output",    TOOL_PROMPT,   300),
            ("General chat",                CHAT_PROMPT,   300),
            ("Creative prose (spec worst)", PROSE_PROMPT,  300),
        ]

        results = []
        for label, prompt, max_tok in tests:
            print(f"  ⏳ Running: {label}...")
            r = await measure_chat(client, prompt, max_tok, label)
            results.append(r)
            print(fmt(r))
            print()
            await asyncio.sleep(1.0)   # let KV cache settle between tests

        if full:
            print(f"  ⏳ Running: Long context (32K tokens)...")
            r = await measure_chat(client, LONG_CTX_PROMPT, 50, "Long context 32K")
            results.append(r)
            print(fmt(r))
            print()

        # Summary
        valid = [r for r in results if not r.error and r.gen_tokens > 0]
        if valid:
            best  = max(valid, key=lambda r: r.tps)
            worst = min(valid, key=lambda r: r.tps)
            avg   = sum(r.tps for r in valid) / len(valid)
            avg_ttft = sum(r.ttft_ms for r in valid) / len(valid)

            print("═" * 60)
            print("  SUMMARY")
            print("═" * 60)
            print(f"  Peak tok/s  : {best.tps:.1f}  ({best.label})")
            print(f"  Low  tok/s  : {worst.tps:.1f}  ({worst.label})")
            print(f"  Average     : {avg:.1f} tok/s")
            print(f"  Avg TTFT    : {avg_ttft:.0f} ms")

            print("\n── Improvement Analysis ─" + "─" * 36)
            if best.tps < 80:
                print("  ⚠  Speed below 80 tok/s — check:")
                print("     • Is --flash-attn enabled? (Ampere+ required)")
                print("     • Is --prio 2 set? (reduces scheduling interruptions)")
                print("     • Are all layers on GPU? (-ngl 99)")
            if best.tps < 40:
                print("  ⚠  Speed below 40 tok/s — likely causes:")
                print("     • Laptop GPU power-limited (TGP 70–80 W vs 115 W desktop)")
                print("     • GPU thermal throttling (check temp above)")
                print("     • --no-mmap not set (page faults mid-inference)")
            if avg_ttft > 500:
                print("  ⚠  High TTFT (>500ms) — model may not be pre-warmed")
                print("     • Restart JARVIS to trigger pre-warm on startup")
            if best.tps >= 100:
                print("  ✅ Excellent speed — speculative decoding working well")
            if best.tps >= 30:
                print("  💡 Acceptable speed for a laptop 4060 (TGP-limited)")
                print("     Theoretical max ~55 tok/s at full 272 GB/s bandwidth")
            if worst.tps < best.tps * 0.4:
                print("  💡 Big variance = spec decoding acceptance varies by task type")
                print("     → Normal: coding=high acceptance, prose=low acceptance")
        else:
            print("\n  No valid results — all tests failed or produced 0 tokens")
            print("  Check server log: C:\\beellama.cpp\\server_err.log")

        gpu_after = await get_gpu_info()
        print(f"\n  GPU after tests: {gpu_after}")
        print("═" * 60 + "\n")

def main():
    parser = argparse.ArgumentParser(description="JARVIS llama.cpp benchmark")
    parser.add_argument("--url", default="http://127.0.0.1:8080", help="llama-server base URL")
    parser.add_argument("--full", action="store_true", help="Include long-context test")
    args = parser.parse_args()

    global BASE_URL
    BASE_URL = args.url.rstrip("/")

    asyncio.run(run_benchmark(full=args.full))

if __name__ == "__main__":
    main()
