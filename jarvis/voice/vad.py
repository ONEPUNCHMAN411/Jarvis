import asyncio
import numpy as np
from loguru import logger

try:
    import torch as _torch
    _HAS_TORCH = True
except ImportError:
    _torch = None
    _HAS_TORCH = False


class VAD:
    def __init__(self, sample_rate: int = 16000, threshold: float = 0.45):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.model = None
        self._ort_session = None  # fallback: onnxruntime session

    async def initialize(self) -> None:
        if _HAS_TORCH:
            try:
                await self._init_torch()
                return
            except Exception as exc:
                logger.warning(f"Silero torch init failed ({exc}), trying ONNX fallback...")
        await self._init_onnx()

    async def _init_torch(self) -> None:
        logger.info("Loading Silero VAD model (torch)...")
        from silero_vad import load_silero_vad
        self.model = await asyncio.to_thread(load_silero_vad)
        logger.info("Silero VAD model loaded (torch)")

    async def _init_onnx(self) -> None:
        logger.info("Loading Silero VAD model (onnxruntime — torch not available)...")
        try:
            import onnxruntime as ort
            import silero_vad as _sv_pkg

            # Find the bundled ONNX file from the silero_vad package
            onnx_path = None
            pkg_path = getattr(_sv_pkg, "__file__", None)
            if pkg_path:
                import os
                candidates = [
                    os.path.join(os.path.dirname(pkg_path), "data", "silero_vad.onnx"),
                    os.path.join(os.path.dirname(pkg_path), "silero_vad.onnx"),
                ]
                for c in candidates:
                    if os.path.exists(c):
                        onnx_path = c
                        break

            if not onnx_path:
                logger.warning("silero_vad ONNX file not found — VAD disabled (passthrough mode)")
                return

            opts = ort.SessionOptions()
            opts.log_severity_level = 3
            self._ort_session = ort.InferenceSession(
                onnx_path,
                sess_options=opts,
                providers=["CPUExecutionProvider"],
            )
            self._h = np.zeros((2, 1, 64), dtype=np.float32)
            self._c = np.zeros((2, 1, 64), dtype=np.float32)
            logger.info("Silero VAD model loaded (onnxruntime)")
        except Exception as e:
            logger.warning(f"VAD onnxruntime init failed: {e} — passthrough mode active")

    def reset_states(self) -> None:
        if self.model is not None:
            try:
                self.model.reset_states()
            except Exception:
                pass
        if self._ort_session is not None:
            self._h = np.zeros((2, 1, 64), dtype=np.float32)
            self._c = np.zeros((2, 1, 64), dtype=np.float32)

    def detect_chunk_sync(self, audio_chunk: np.ndarray) -> float:
        normalized = audio_chunk.astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(np.square(normalized))))
        if rms < 0.0008:
            return 0.0

        if self.model is not None and _HAS_TORCH:
            try:
                audio_tensor = _torch.from_numpy(normalized).float()
                if audio_tensor.dim() > 1:
                    audio_tensor = audio_tensor.squeeze()
                prob = float(self.model(audio_tensor, self.sample_rate).detach())
                if prob < 0.10:
                    try:
                        self.model.reset_states()
                    except Exception:
                        pass
                return prob
            except Exception as exc:
                logger.debug(f"VAD chunk error: {exc}")
                return 0.0

        if self._ort_session is not None:
            try:
                chunk = normalized[:512] if len(normalized) >= 512 else np.pad(normalized, (0, 512 - len(normalized)))
                chunk = chunk[np.newaxis, :]  # (1, 512)
                sr = np.array(self.sample_rate, dtype=np.int64)
                out, self._h, self._c = self._ort_session.run(
                    None,
                    {"input": chunk, "h": self._h, "c": self._c, "sr": sr},
                )
                prob = float(out[0][0])
                if prob < 0.10:
                    self.reset_states()
                return prob
            except Exception as exc:
                logger.debug(f"VAD onnx chunk error: {exc}")
                return 0.0

        # Passthrough: no model available — treat all audio above RMS gate as speech
        return 0.6 if rms > 0.003 else 0.0

    async def detect_chunk(self, audio_chunk: np.ndarray) -> float:
        return self.detect_chunk_sync(audio_chunk)

    async def detect_voice_activity(self, audio_chunk: np.ndarray) -> bool:
        prob = await self.detect_chunk(audio_chunk)
        return prob >= self.threshold

    async def get_voice_segments(self, audio_data: np.ndarray) -> list[dict]:
        if self.model is None and self._ort_session is None:
            duration_s = len(audio_data) / self.sample_rate
            return [{"start": 0.0, "end": duration_s}]

        if self.model is not None and _HAS_TORCH:
            from silero_vad import get_speech_timestamps
            audio_tensor = _torch.from_numpy(audio_data.astype(np.float32) / 32768.0).float()
            if audio_tensor.dim() > 1:
                audio_tensor = audio_tensor.squeeze()
            try:
                segments = await asyncio.to_thread(
                    get_speech_timestamps,
                    audio_tensor,
                    self.model,
                    return_seconds=True,
                )
                return segments
            except Exception as e:
                logger.error(f"VAD segmentation error: {e}")
                return []

        # onnxruntime path — slide window
        audio_float = audio_data.astype(np.float32) / 32768.0
        duration_s = len(audio_float) / self.sample_rate
        chunk_size = 512
        probs = []
        for i in range(0, len(audio_float), chunk_size):
            chunk = audio_float[i:i + chunk_size]
            if len(chunk) < chunk_size:
                chunk = np.pad(chunk, (0, chunk_size - len(chunk)))
            probs.append(self.detect_chunk_sync((chunk * 32768).astype(np.int16)))

        segments: list[dict] = []
        in_speech = False
        start = 0.0
        chunk_dur = chunk_size / self.sample_rate
        for idx, p in enumerate(probs):
            t = idx * chunk_dur
            if p >= self.threshold and not in_speech:
                in_speech = True
                start = t
            elif p < self.threshold and in_speech:
                in_speech = False
                segments.append({"start": start, "end": t})
        if in_speech:
            segments.append({"start": start, "end": duration_s})
        return segments

    async def shutdown(self) -> None:
        self.model = None
        self._ort_session = None
        logger.info("VAD model shutdown")
