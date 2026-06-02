import asyncio
import numpy as np
import sounddevice as sd
from loguru import logger

class AudioCapture:
    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_size: int = 512,
        channels: int | None = None,
        dtype: str = "int16",
        device: int | None = None,
        level_callback=None,
        max_queue_chunks: int = 256,
    ):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.channels = channels
        self.dtype = dtype
        self.device = device
        self.level_callback = level_callback
        self.max_queue_chunks = max(8, int(max_queue_chunks))
        self.is_listening = False
        self._stream = None
        self._queue = None
        self._loop = None

    async def start(self) -> None:
        self.is_listening = True
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(maxsize=self.max_queue_chunks)
        logger.info(f"Starting audio capture at {self.sample_rate}Hz")

        def audio_callback(indata, frames, time, status):
            if status:
                logger.warning(f"Audio status: {status}")

            # Extract channel 0 to guarantee mono (STT requires 1D array)
            if indata.ndim > 1 and indata.shape[1] > 1:
                chunk = indata[:, 0].copy()
            else:
                chunk = indata.copy().reshape(-1)

            if self.level_callback:
                try:
                    normalized = chunk.astype(np.float32) / 32768.0
                    level = float(np.sqrt(np.mean(np.square(normalized))))
                    self.level_callback(level)
                except Exception as exc:
                    logger.debug(f"Audio level callback failed: {exc}")

            if self._loop and not self._loop.is_closed() and self._queue:
                try:
                    self._loop.call_soon_threadsafe(self._enqueue_chunk, chunk)
                except RuntimeError:
                    pass

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            device=self.device,
            blocksize=self.chunk_size,
            callback=audio_callback,
            latency="low",
        )
        self._stream.start()
        logger.info("Audio stream started")

    async def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.is_listening = False
        self._queue = None
        self._loop = None
        logger.info("Audio capture stopped")

    def _enqueue_chunk(self, chunk: np.ndarray) -> None:
        """
        Keep the freshest chunks when the app is busy so the queue cannot grow
        into tens of seconds of stale microphone audio.
        """
        if self._queue is None:
            return
        while self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        try:
            self._queue.put_nowait(chunk)
        except asyncio.QueueFull:
            pass

    async def get_audio_chunk(self) -> np.ndarray:
        if not self.is_listening or self._queue is None:
            raise RuntimeError("Audio capture not started")
        return await self._queue.get()

    async def get_audio_duration(self, duration_ms: int) -> np.ndarray:
        num_chunks = (duration_ms * self.sample_rate) // (1000 * self.chunk_size)
        chunks = []
        for _ in range(num_chunks):
            chunk = await self.get_audio_chunk()
            chunks.append(chunk)

        if chunks:
            return np.concatenate(chunks, axis=0)
        return np.array([], dtype=self.dtype)
