import asyncio
import re
import numpy as np
from loguru import logger

# NOTE: CUDA DLL paths are registered in jarvis/__main__.py before any import.
# Do NOT add os.add_dll_directory() here — ctranslate2 is already loaded by now.
from faster_whisper import WhisperModel

def _cuda_available() -> bool:
    """Return True only if ctranslate2 was compiled with CUDA support AND a GPU is visible."""
    try:
        import ctranslate2
        types = ctranslate2.get_supported_compute_types("cuda")
        if not types:
            return False
        # Double-check a real GPU is present via torch (optional dep)
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return True   # ctranslate2 says yes, trust it
    except Exception as exc:
        logger.debug(f"CUDA check failed: {exc}")
        return False

# Biases Whisper toward JARVIS-related vocabulary so it stops mishearing
# "hey jarvis" as random words, and understands common commands correctly.
_INITIAL_PROMPT = (
    "JARVIS. Hey JARVIS. Open, close, launch, search, navigate, go to, "
    "what time, weather, volume, screenshot, clipboard, calculate, type, "
    "press, write, read file, run, show me, tell me, what is, how do I."
)

# Whisper hallucinates these phrases on silence/background noise.
# Any transcription that reduces to one of these (case/punct-insensitive) is discarded.
_HALLUCINATED_PHRASES: frozenset[str] = frozenset({
    "okay", "ok", "yes", "no", "hmm", "mm", "um", "uh", "ah",
    "thanks", "thank you", "thank you for watching",
    "bye", "bye bye", "goodbye", "see you",
    "sure", "right", "alright", "all right",
    "you", "hey", "huh", "oh", "so",
    "i", "the", "a",
    ".", "..", "...", "…",
    "subtitles by", "subtitles by the amara",
    "captions by", "closed captioning",
    "transcribed by", "this video",
})

def _is_hallucination(text: str) -> bool:
    """Return True if text is a known Whisper phantom phrase."""
    normalized = re.sub(r"[^a-z0-9 ]", "", text.strip().lower()).strip()
    return not normalized or normalized in _HALLUCINATED_PHRASES

class STT:
    def __init__(self, model_name: str = "medium.en", device: str = "auto", compute_type: str = "auto", language: str = "en"):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.model = None
        self._cuda_failure_count: int = 0
        self._permanently_on_cpu: bool = False
        self._recovery_task: asyncio.Task | None = None

        # GPU-busy flag — set True when another process (Ollama, llamacpp) is using the GPU.
        # Transcription routes to _cpu_fallback_model while this is True, avoiding CUDA
        # kernel conflicts and out-of-memory errors that cause 45-second stalls.
        self._gpu_busy: bool = False
        self._cpu_fallback_model = None   # pre-loaded CPU int8 model, always available

    def set_gpu_busy(self, busy: bool) -> None:
        """Called by the app when a local GPU provider starts/stops inference.
        When busy=True, transcription is routed to the CPU fallback model so Whisper
        and Ollama/llamacpp don't compete for CUDA kernels."""
        self._gpu_busy = busy
        logger.debug(f"STT gpu_busy → {busy}")

    async def initialize(self) -> None:
        logger.info(
            f"Loading Whisper model: {self.model_name} — "
            "first run may download the model, please wait…"
        )
        if self.device == "auto":
            if _cuda_available():
                logger.info("CUDA GPU detected — using float16 acceleration")
                candidates = [("cuda", "float16"), ("cpu", "int8")]
            else:
                logger.info("No CUDA GPU detected — using CPU/int8 (install CUDA drivers + ctranslate2[cuda] for GPU)")
                candidates = [("cpu", "int8")]
        else:
            compute = self.compute_type if self.compute_type != "auto" else "float16"
            candidates = [(self.device, compute), ("cpu", "int8")]

        last_error = None
        for device, compute_type in candidates:
            try:
                self.model = await self._create_model(device, compute_type)
                await self._probe_model(self.model)
                self.device = device
                self.compute_type = compute_type
                logger.info(f"Whisper model loaded on {device}/{compute_type}")
                break
            except Exception as exc:
                last_error = exc
                logger.warning(f"Whisper load failed on {device}/{compute_type}: {exc}")
        else:
            raise RuntimeError(f"Unable to initialize STT: {last_error}")

        # Pre-load a CPU int8 fallback model so we can switch instantly when GPU is busy.
        # Only needed when the primary model is on CUDA — if already on CPU, skip.
        if self.device == "cuda":
            logger.info("Pre-loading Whisper CPU fallback model for GPU-contention resilience…")
            try:
                self._cpu_fallback_model = await self._create_model("cpu", "int8")
                logger.info("Whisper CPU fallback model ready (used when Ollama/llamacpp holds the GPU)")
            except Exception as exc:
                logger.warning(f"CPU fallback model failed to load (non-fatal): {exc}")
                self._cpu_fallback_model = None

    # Maximum seconds to wait for a single transcription before giving up.
    # tiny.en on CPU: ~1-3s.  medium.en on CPU: up to 20s on slow machines.
    _TRANSCRIBE_TIMEOUT = 45.0
    # CPU path gets a shorter timeout — if it takes >15s something is very wrong.
    _CPU_TIMEOUT = 20.0

    async def transcribe(self, audio_data: np.ndarray, sample_rate: int = 16000) -> str:
        if self.model is None:
            raise RuntimeError("STT model not initialized")

        duration_s = len(audio_data) / sample_rate

        # GPU-busy path
        # When Ollama / llamacpp is holding the GPU, route to the pre-loaded CPU
        # fallback model instead of the CUDA model.  This prevents ctranslate2 and
        # the LLM backend from fighting for CUDA kernels, which causes 45-second
        # stalls and eventual timeout failures.
        if self._gpu_busy and self._cpu_fallback_model is not None:
            logger.debug(f"GPU busy — transcribing {duration_s:.1f}s on CPU fallback")
            try:
                text = await asyncio.wait_for(
                    self._transcribe_with_model(self._cpu_fallback_model, audio_data, sample_rate),
                    timeout=self._CPU_TIMEOUT,
                )
                logger.info(f"Transcription (cpu-fallback, gpu_busy): {text!r}")
                return text
            except asyncio.TimeoutError:
                logger.error(f"CPU fallback transcription timed out after {self._CPU_TIMEOUT}s")
                return ""
            except Exception as exc:
                logger.warning(f"CPU fallback transcription failed: {exc} — trying main model")
                # Fall through to main model attempt below

        logger.debug(f"Transcribing {duration_s:.1f}s of audio on {self.device}")

        # CUDA primary path
        if self.device == "cuda" and not self._permanently_on_cpu:
            for attempt in range(3):
                try:
                    text = await asyncio.wait_for(
                        self._transcribe_with_model(self.model, audio_data, sample_rate),
                        timeout=self._TRANSCRIBE_TIMEOUT,
                    )
                    self._cuda_failure_count = 0
                    logger.info(f"Transcription (cuda): {text!r}")
                    return text
                except asyncio.TimeoutError:
                    logger.error(f"CUDA transcription timed out after {self._TRANSCRIBE_TIMEOUT}s — falling back to CPU")
                    self._permanently_on_cpu = True
                    await self._reload_cpu_model()
                    self._schedule_cuda_recovery()
                    break
                except RuntimeError as exc:
                    self._cuda_failure_count += 1
                    if attempt < 2:
                        logger.warning(f"CUDA transcription error (attempt {attempt+1}/3): {exc} — retrying in 0.5s")
                        await asyncio.sleep(0.5)
                    else:
                        logger.error(f"CUDA failed 3 times, falling back to CPU: {exc}")
                        self._permanently_on_cpu = True
                        await self._reload_cpu_model()
                        self._schedule_cuda_recovery()

        # CPU primary / permanent-fallback path
        try:
            text = await asyncio.wait_for(
                self._transcribe_with_model(self.model, audio_data, sample_rate),
                timeout=self._TRANSCRIBE_TIMEOUT,
            )
            logger.info(f"Transcription ({self.device}): {text!r}")
            return text
        except asyncio.TimeoutError:
            logger.error(f"Transcription timed out after {self._TRANSCRIBE_TIMEOUT}s — returning empty string")
            return ""

    async def _create_model(self, device: str, compute_type: str):
        kwargs: dict = {"device": device, "compute_type": compute_type}
        if device == "cpu":
            # Scale threads to available cores (capped at 8 to avoid diminishing returns)
            import os as _os
            kwargs["cpu_threads"] = min(_os.cpu_count() or 4, 8)
        return await asyncio.to_thread(
            WhisperModel,
            self.model_name,
            **kwargs,
        )

    async def _probe_model(self, model) -> None:
        probe_audio = np.zeros(16000, dtype=np.int16)
        await self._transcribe_with_model(model, probe_audio, 16000)

    async def _reload_cpu_model(self) -> None:
        self.model = await self._create_model("cpu", "int8")
        self.device = "cpu"
        self.compute_type = "int8"
        logger.info("Whisper model reloaded on cpu/int8 after CUDA failure")

    def _schedule_cuda_recovery(self) -> None:
        """Try to recover CUDA after 2 minutes — GPU may have freed memory by then."""
        if self._recovery_task and not self._recovery_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
            self._recovery_task = loop.create_task(self._try_cuda_recover())
        except RuntimeError:
            pass

    async def _try_cuda_recover(self) -> None:
        await asyncio.sleep(120)
        logger.info("Attempting to recover Whisper CUDA model after 2-minute cooldown…")
        try:
            candidate = await self._create_model("cuda", "float16")
            await self._probe_model(candidate)
            self.model = candidate
            self.device = "cuda"
            self.compute_type = "float16"
            self._permanently_on_cpu = False
            self._cuda_failure_count = 0
            logger.info("Whisper CUDA model recovered successfully")
        except Exception as exc:
            logger.warning(f"CUDA recovery failed, staying on CPU: {exc}")

    @staticmethod
    def _preprocess_audio(audio_data: np.ndarray) -> np.ndarray:
        """Convert int16 → float32 for Whisper.  No pre-emphasis: Whisper was
        trained on raw internet audio and applies its own mel-filterbank
        weighting internally.  Pre-emphasis distorts the spectrum enough that
        Whisper raises no_speech_prob on real speech and drops the transcript."""
        audio = audio_data.astype(np.float32) / 32768.0
        peak = np.max(np.abs(audio))
        if peak > 0.01:
            audio = audio * (0.9 / peak)
        return audio

    async def _transcribe_with_model(
        self,
        model,
        audio_data: np.ndarray,
        sample_rate: int = 16000,
    ) -> str:
        audio_float = self._preprocess_audio(audio_data)

        # Adaptive beam size: quick commands (<3s) use beam=1 for ~40% speed gain,
        # longer utterances use beam=3 for better accuracy.
        duration_s = len(audio_float) / sample_rate
        _beam = 1 if duration_s < 3.0 else 3

        def run_transcribe():
            segments, info = model.transcribe(
                audio_float,
                language=self.language,
                beam_size=_beam,
                best_of=1,
                # VAD filter skips silent regions — reduces hallucinations on noise
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 200},
                condition_on_previous_text=False,
                temperature=0.0,
                # Bias Whisper toward JARVIS vocabulary
                initial_prompt=_INITIAL_PROMPT,
                # Suppress common hallucinations on silence
                suppress_blank=True,
                # lower threshold = more sensitive to any speech-like sound
                no_speech_threshold=0.4,
                word_timestamps=False,
                # Skip recomputation on low-confidence segments
                log_prob_threshold=-1.0,
            )
            parts: list[str] = []
            for seg in segments:
                # Only skip segments where Whisper is overwhelmingly sure it's not speech
                if getattr(seg, "no_speech_prob", 0.0) > 0.95:
                    logger.debug(f"Skipped silent segment (no_speech={seg.no_speech_prob:.2f}): {seg.text!r}")
                    continue
                parts.append(seg.text)

            raw = " ".join(parts).strip()
            if _is_hallucination(raw):
                logger.debug(f"Discarded hallucination: {raw!r}")
                return ""
            return raw

        return await asyncio.to_thread(run_transcribe)

    async def shutdown(self) -> None:
        logger.info("STT model shutdown")
