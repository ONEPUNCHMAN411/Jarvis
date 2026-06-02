import asyncio
import re
from collections import deque
import numpy as np
from loguru import logger

from jarvis.event_bus import EventBus
from jarvis.models import MicLevelEvent, RuntimeLogEvent, StatusEvent, TTSRequestEvent, UserSpeechEvent
from jarvis.voice.utterance import extract_command_from_transcript, is_meaningful_transcript
from jarvis.voice.audio_capture import AudioCapture
from jarvis.voice.audio_player import AudioPlayer
from jarvis.voice.voice_profiles import get_voice_profile
from jarvis.voice.stt import STT
from jarvis.voice.tts import TTS
from jarvis.voice.vad import VAD
from jarvis.voice.wake_word import WakeWordDetector

# Chunk size = 512 samples @ 16 kHz → 32 ms per chunk
_MS_PER_CHUNK = 32

# Hard trailing timeout: if last VAD-confirmed speech was this many seconds ago, stop.
# Increased from 0.60 → 1.2 s so a natural mid-sentence pause ("Hey JARVIS, [pause]
# can you open X") is not cut off before the rest of the command arrives.
_TRAILING_TIMEOUT_S = 1.2

def _silence_chunks_needed(speech_elapsed_s: float) -> int:
    """
    Silence duration in 32 ms chunk units before end-of-utterance (when VAD is borderline).
    These are the *normal* path values; the hard trailing timeout and deep-silence
    gates below will cut listening faster when the mic is clearly dead.
    """
    if speech_elapsed_s < 0.8:
        return 12   # ~384 ms — short commands (was 6/192 ms)
    elif speech_elapsed_s < 2.0:
        return 8    # ~256 ms (was 5/160 ms)
    else:
        return 6    # ~192 ms — long utterance (was 4/128 ms)

class VoiceManager:
    def __init__(
        self,
        event_bus: EventBus,
        config,
        voice_profile_id: str = "jarvis",
        custom_voice_profile: dict | None = None,
    ):
        self.event_bus = event_bus
        self.config = config
        self.loop = None
        self.voice_profile_id = voice_profile_id
        self.custom_voice_profile = custom_voice_profile

        voice_profile = get_voice_profile(voice_profile_id, custom_voice_profile)

        self.audio_capture = AudioCapture(
            sample_rate=16000,
            device=config.voice.input_device,
            level_callback=self._on_audio_level,
        )
        self.audio_player = AudioPlayer(
            sample_rate=24000,
            device=config.voice.output_device,
        )
        self.stt = STT(model_name=config.voice.stt_model)
        self.tts = TTS(
            voice=voice_profile["voice"],
            rate=voice_profile["rate"],
            pitch=voice_profile["pitch"],
        )
        self.vad = VAD()
        self.wake_word = WakeWordDetector(
            wake_word=config.voice.wake_word,
            sensitivity=config.voice.wake_word_sensitivity,
        )

        self.is_running = False
        self.enabled = bool(config.voice.enabled)
        self.background_mode = "always_listening" if config.voice.always_listening else "wake_phrase"
        self.backgrounded = False
        self._is_processing = False
        self._last_audio_level = 0.0
        self._last_speech_detected = False
        self._last_meter_emit = 0.0
        self._status = "idle"
        self._tts_interrupted = False
        self.listener_task = None
        self.mode = self._effective_mode()

        # Adaptive noise-floor — calibrated at startup, then updated via slow EMA during silence
        self._rms_floor: float = 0.008
        # Minimum gap between dispatched commands (prevents always-listening from spamming)
        self._last_command_time: float = 0.0
        self._min_command_gap_s: float = 2.0
        # Audio buffered during a TTS barge-in for seamless transcription
        self._barge_in_buffer: list = []

    async def initialize(self) -> None:
        logger.info("Initializing voice manager...")
        self.loop = asyncio.get_running_loop()
        try:
            await self.stt.initialize()
        except Exception as exc:
            logger.error(f"STT initialization failed: {exc}")
            await self.event_bus.publish(
                RuntimeLogEvent("error", f"Speech-to-text failed to load: {exc}. Voice input disabled.")
            )
            self.enabled = False

        try:
            await self.vad.initialize()
        except Exception as exc:
            logger.warning(f"VAD initialization failed (disabled): {exc}")
            self.vad = None

        try:
            await self.wake_word.initialize()
            if self.wake_word.fallback_mode:
                await self.event_bus.publish(RuntimeLogEvent(
                    "warning",
                    "Wake word unavailable — say nothing, just click 🎤 or press Ctrl+Shift+J to talk."
                ))
        except Exception as exc:
            logger.warning(f"Wake word initialization failed: {exc}")

        try:
            await self.audio_capture.start()
        except Exception as exc:
            logger.error(f"Microphone init failed: {exc}")
            await self.event_bus.publish(
                RuntimeLogEvent("error", f"Microphone unavailable: {exc}. Voice input disabled.")
            )
            self.enabled = False

        self.is_running = True
        self.event_bus.subscribe(TTSRequestEvent, self.on_tts_request)

        # Log which mic device is active so the user can diagnose wrong device issues
        try:
            import sounddevice as sd
            dev = sd.query_devices(sd.default.device[0] if self.config.voice.input_device is None
                                   else self.config.voice.input_device)
            await self.event_bus.publish(
                RuntimeLogEvent("info", f"Microphone: {dev['name']} ({int(dev['default_samplerate'])} Hz)")
            )
        except Exception:
            pass

        await self._calibrate_noise_floor()
        await self.event_bus.publish(RuntimeLogEvent("info", "Voice manager initialized"))

        if self.enabled:
            await self.start_listening()

    async def _calibrate_noise_floor(self) -> None:
        """
        Record ~1.5 s of ambient audio at startup, compute the 95th-percentile
        RMS across all chunks, then set the speech threshold to 5× that value.
        This adapts to quiet rooms, loud offices, and noisy headsets automatically.
        Floor is clamped to [0.004, 0.030].
        """
        try:
            await self.event_bus.publish(RuntimeLogEvent("info", "Calibrating microphone noise floor…"))
            n_chunks = 48  # 48 × 32 ms = 1536 ms
            rms_values: list[float] = []
            for _ in range(n_chunks):
                try:
                    chunk = await asyncio.wait_for(self.audio_capture.get_audio_chunk(), timeout=0.5)
                    normalized = chunk.astype(np.float32) / 32768.0
                    rms_values.append(float(np.sqrt(np.mean(np.square(normalized)))))
                except asyncio.TimeoutError:
                    break

            if rms_values:
                rms_values.sort()
                p95 = rms_values[int(len(rms_values) * 0.95)]
                self._rms_floor = max(0.004, min(p95 * 5.0, 0.030))
                if self.vad:
                    self.vad.threshold = max(0.35, min(0.55, 0.40 + p95 * 10.0))

            await self.event_bus.publish(
                RuntimeLogEvent("info", f"Noise floor calibrated: RMS threshold={self._rms_floor:.4f}")
            )
        except Exception as exc:
            logger.warning(f"Noise calibration failed (using default): {exc}")

    async def shutdown(self) -> None:
        logger.info("Shutting down voice manager...")
        await self.stop_listening()
        await self.audio_capture.stop()
        await self.stt.shutdown()
        if self.vad:
            await self.vad.shutdown()
        await self.wake_word.shutdown()
        self.is_running = False
        logger.info("Voice manager shutdown")

    async def start_listening(self) -> None:
        if not self.is_running or not self.enabled:
            return
        await self.stop_listening()
        self.mode = self._effective_mode()
        self.listener_task = asyncio.create_task(self._listener_loop())

    async def stop_listening(self) -> None:
        if self.listener_task:
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass
            self.listener_task = None

    async def set_processing(self, processing: bool) -> None:
        """Sets whether the assistant is currently processing a request."""
        self._is_processing = processing
        if processing:
            # If we were capturing, we might want to stop, but the loop
            # will naturally wait at the next _capture_phrase call.
            pass

    def set_gpu_busy(self, busy: bool) -> None:
        """Notify the STT engine that a local GPU provider (Ollama, llamacpp) is
        actively running inference.  When busy=True, Whisper transcription is routed
        to the pre-loaded CPU int8 fallback model, preventing CUDA kernel contention
        that causes 45-second stalls and timeout failures."""
        if hasattr(self, "stt") and self.stt is not None:
            self.stt.set_gpu_busy(busy)

    async def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if enabled:
            await self.start_listening()
        else:
            await self.stop_listening()
            await self._publish_status("idle")

    async def set_mode(self, mode: str) -> None:
        self.background_mode = mode
        if self.enabled:
            await self.start_listening()

    async def set_backgrounded(self, backgrounded: bool) -> None:
        self.backgrounded = backgrounded
        if self.enabled:
            await self.start_listening()

    async def set_wake_word_sensitivity(self, sensitivity: float) -> None:
        self.wake_word.sensitivity = max(0.1, min(1.0, sensitivity))
        if self.vad:
            self.vad.threshold = max(0.30, min(0.65, 0.35 + (1.0 - sensitivity) * 0.15))

    async def reload_stt(self, model: str, language: str = "en") -> None:
        if model == self.stt.model_name and language == getattr(self.stt, "language", "en"):
            return
        await self.stop_listening()
        await self.stt.shutdown()
        self.stt = STT(model_name=model, language=language)
        await self.event_bus.publish(RuntimeLogEvent("info", f"Loading Whisper model: {model}…"))
        try:
            await self.stt.initialize()
            await self.event_bus.publish(RuntimeLogEvent("info", f"STT model loaded: {model}"))
        except Exception as exc:
            logger.error(f"STT reload failed: {exc}")
            await self.event_bus.publish(RuntimeLogEvent("error", f"STT reload failed: {exc}"))
        if self.enabled:
            await self.start_listening()

    async def set_input_device(self, device) -> None:
        await self.stop_listening()
        await self.audio_capture.stop()
        self.audio_capture = AudioCapture(
            sample_rate=16000,
            device=device,
            level_callback=self._on_audio_level,
        )
        try:
            await self.audio_capture.start()
            await self.event_bus.publish(RuntimeLogEvent("info", f"Microphone switched to device {device!r}"))
        except Exception as exc:
            logger.error(f"Audio capture restart failed: {exc}")
            await self.event_bus.publish(RuntimeLogEvent("error", f"Mic device change failed: {exc}"))
        if self.enabled:
            await self.start_listening()

    async def set_voice_profile(self, profile_id: str, custom_profile: dict | None = None) -> None:
        self.custom_voice_profile = custom_profile or self.custom_voice_profile
        profile = get_voice_profile(profile_id, self.custom_voice_profile)
        self.voice_profile_id = profile["id"]
        self.tts.set_voice(
            profile["voice"],
            rate=profile["rate"],
            pitch=profile["pitch"],
        )
        await self.event_bus.publish(
            RuntimeLogEvent("info", f"Voice profile set to {profile['label']}")
        )

    async def preview_voice(self, text: str = "Systems online. Awaiting your command, sir.") -> None:
        await self.on_tts_request(TTSRequestEvent(text=text))

    async def on_tts_request(self, event: TTSRequestEvent):
        try:
            self._tts_interrupted = False
            await self._publish_status("speaking")

            # Cap TTS to avoid reading enormous responses aloud.
            # Find a sentence boundary near the 500-char limit so we don't cut mid-word.
            _MAX_TTS_CHARS = 500
            tts_text = event.text.strip()
            if len(tts_text) > _MAX_TTS_CHARS:
                cutoff = tts_text.rfind('. ', 0, _MAX_TTS_CHARS)
                if cutoff < 80:
                    cutoff = _MAX_TTS_CHARS
                tts_text = tts_text[: cutoff + 1]

            sentences = [s.strip() for s in re.split(r'(?<=[.!?]) +', tts_text) if s.strip()]
            if not sentences:
                return

            audio_queue = asyncio.Queue(maxsize=5)

            async def synthesizer():
                try:
                    for sentence in sentences:
                        if not self.is_running or self._tts_interrupted:
                            break
                        audio = await self.tts.synthesize(sentence)
                        if audio:
                            await audio_queue.put(audio)
                    await audio_queue.put(None)
                except Exception as e:
                    logger.error(f"Synthesizer error: {e}")
                    await audio_queue.put(None)

            synth_task = asyncio.create_task(synthesizer())

            while True:
                if self._tts_interrupted:
                    logger.info("TTS interrupted by user speech")
                    break
                audio_bytes = await audio_queue.get()
                if audio_bytes is None:
                    break
                await self.audio_player.play_audio(audio_bytes)

            await synth_task

        except Exception as exc:
            logger.error(f"TTS playback error: {exc}")
            await self.event_bus.publish(RuntimeLogEvent("error", f"Voice output failed: {exc}"))
        finally:
            # ALWAYS return to idle — never leave the orb stuck on 'speaking'
            self._tts_interrupted = False
            await self._publish_status("idle")

    async def _listener_loop(self) -> None:
        await self.event_bus.publish(
            RuntimeLogEvent("info", f"Voice mode active: {self.mode}")
        )
        while self.is_running and self.enabled:
            try:
                if self.mode == "always_listening":
                    await self._always_listening_mode()
                else:
                    await self._wake_word_mode()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"Voice listener failed: {exc} — restarting in 1s")
                await self._publish_status("error")
                await asyncio.sleep(1.0)
                if self.vad is not None:
                    self.vad.reset_states()
                self._drain_stale_audio()
                await self._publish_status("idle")

    def _drain_stale_audio(self) -> None:
        """
        Discard audio that piled up while the model was processing or TTS was playing.
        Without this, JARVIS might transcribe its own voice or several seconds of
        room noise as the next command.
        """
        q = self.audio_capture._queue
        if q is None:
            return
        drained = 0
        while not q.empty():
            try:
                q.get_nowait()
                drained += 1
            except Exception:
                break
        if drained:
            logger.debug(f"Drained {drained} stale audio chunks ({drained * 32} ms)")

    async def _always_listening_mode(self) -> None:
        while self.is_running and self.enabled:
            if self._is_processing:
                await asyncio.sleep(0.05)
                continue

            # Enforce minimum gap between commands to prevent spam on ambient noise
            gap = self.loop.time() - self._last_command_time
            if gap < self._min_command_gap_s:
                await asyncio.sleep(min(0.05, self._min_command_gap_s - gap))
                continue

            # While TTS is playing, check for barge-in speech
            self._barge_in_buffer = []
            if self.audio_player.is_playing:
                chunk = await self._check_tts_interrupt()
                if chunk is not None:
                    # Interrupt detected — buffer remaining speech while TTS winds down
                    self._barge_in_buffer.append(chunk)
                    while self.audio_player.is_playing:
                        try:
                            c = await asyncio.wait_for(
                                self.audio_capture.get_audio_chunk(), timeout=0.05
                            )
                            self._barge_in_buffer.append(c)
                        except (asyncio.TimeoutError, Exception):
                            break
                else:
                    await asyncio.sleep(0.05)
                    continue

            # Only drain stale audio when there's no barge-in speech to keep
            if not self._barge_in_buffer:
                self._drain_stale_audio()

            text = await self._capture_phrase(pre_buffer=self._barge_in_buffer or None)
            if text and is_meaningful_transcript(text):
                self._last_command_time = self.loop.time()
                await self.event_bus.publish(
                    UserSpeechEvent(text=text, confidence=1.0, timestamp=0.0)
                )
            await self._publish_status("idle")

    async def _wake_word_mode(self) -> None:
        while self.is_running and self.enabled:
            if self.audio_player.is_playing or self._is_processing:
                await asyncio.sleep(0.05)
                continue
            self._drain_stale_audio()
            phrase = await self._capture_phrase()
            if not phrase:
                continue

            command = extract_command_from_transcript(
                transcript=phrase,
                wake_phrase=self.config.voice.wake_word,
                require_wake_phrase=True,
            )

            if not command:
                # Wake word heard but no command followed. Log it so the user can
                # see that detection is working, then wait for the next phrase.
                logger.info(f"Wake word detected (no command): {phrase!r}")
                await self.event_bus.publish(
                    RuntimeLogEvent("info", "Wake word detected — say your command now")
                )
                continue

            logger.info(f"Wake phrase detected: {phrase!r} -> command: {command!r}")
            if is_meaningful_transcript(command):
                await self.event_bus.publish(
                    UserSpeechEvent(text=command, confidence=1.0, timestamp=0.0)
                )
            await self._publish_status("idle")

    async def _check_tts_interrupt(self):
        """
        Sample a mic chunk while TTS plays. If VAD detects speech, interrupt TTS
        and return the triggering chunk so the caller can begin barge-in buffering.
        Returns the audio chunk on interrupt, None otherwise.
        """
        try:
            chunk = await asyncio.wait_for(self.audio_capture.get_audio_chunk(), timeout=0.1)
            if self.vad is not None:
                prob = self.vad.detect_chunk_sync(chunk)
                if prob >= self.vad.threshold:
                    self._tts_interrupted = True
                    self.audio_player.stop()
                    logger.info("User speech detected during TTS — interrupting for barge-in")
                    return chunk
        except (asyncio.TimeoutError, Exception):
            pass
        return None

    async def _capture_phrase(self, pre_buffer: list | None = None) -> str:
        """
        Three-tier end-of-speech detection:

        1. Fast exit — low VAD probability for 2 consecutive chunks (~64 ms).
        2. Normal exit — silence_count hits _silence_chunks_needed().
        3. Hard trailing timeout — if 600 ms elapsed since last speech chunk, done.

        pre_buffer: barge-in audio already captured during TTS playback; when provided
        the phrase is considered already started so pre-roll is skipped.
        """
        if self.vad is not None:
            self.vad.reset_states()

        audio_buffer: list[np.ndarray] = []
        pre_roll: deque = deque(maxlen=8)   # ~256 ms pre-roll
        silence_count = 0
        deep_silence_count = 0   # consecutive chunks where VAD prob is clearly low
        rms_quiet_count = 0      # consecutive chunks with low mic energy
        speech_chunk_count = 0
        speech_started = False
        speech_start_time: float | None = None
        last_speech_time: float | None = None  # time of last VAD-confirmed speech chunk
        last_vad_prob: float = 0.0
        chunk_rms: float = 0.0

        max_capture_time = 30.0
        min_speech_chunks = 2           # 64 ms minimum to count as speech
        min_audio_samples = int(self.audio_capture.sample_rate * 0.28)
        start_time = self.loop.time()

        # Seed from barge-in: treat already-captured chunks as started speech
        if pre_buffer:
            audio_buffer.extend(pre_buffer)
            speech_started = True
            speech_chunk_count = len(pre_buffer)
            speech_start_time = self.loop.time()
            last_speech_time = self.loop.time()
            await self._publish_status("listening")

        try:
            while self.is_running and self.enabled:
                chunk = await asyncio.wait_for(
                    self.audio_capture.get_audio_chunk(),
                    timeout=1.0,
                )
                pre_roll.append(chunk)

                normalized_f = chunk.astype(np.float32) / 32768.0
                chunk_rms = float(np.sqrt(np.mean(np.square(normalized_f))))

                # Get both the binary flag and the raw probability in one call
                if self.vad is not None:
                    last_vad_prob = self.vad.detect_chunk_sync(chunk)
                    has_speech = last_vad_prob >= self.vad.threshold
                else:
                    has_speech = chunk_rms >= self._rms_floor
                    last_vad_prob = 1.0 if has_speech else 0.0

                self._last_speech_detected = has_speech

                # Adaptive noise floor EMA: slowly track ambient level during pre-speech
                if not speech_started and chunk_rms < self._rms_floor * 3:
                    self._rms_floor = self._rms_floor * 0.995 + chunk_rms * 0.005
                    self._rms_floor = max(0.004, min(self._rms_floor, 0.030))

                if self.loop.time() - start_time > max_capture_time:
                    break

                if has_speech:
                    if not speech_started:
                        speech_started = True
                        speech_start_time = self.loop.time()
                        audio_buffer.extend(list(pre_roll))
                        await self._publish_status("listening")
                    else:
                        audio_buffer.append(chunk)
                    last_speech_time = self.loop.time()
                    silence_count = 0
                    deep_silence_count = 0
                    rms_quiet_count = 0
                    speech_chunk_count += 1

                elif speech_started:
                    audio_buffer.append(chunk)
                    silence_count += 1

                    # Deep silence: VAD prob well below threshold (catches Silero LSTM tail)
                    if last_vad_prob < 0.30:
                        deep_silence_count += 1
                    else:
                        deep_silence_count = 0

                    # RMS gate: mic energy collapsed near noise floor
                    if chunk_rms <= self._rms_floor * 2.5:
                        rms_quiet_count += 1
                    else:
                        rms_quiet_count = 0

                    elapsed_speech = self.loop.time() - speech_start_time  # type: ignore[operator]

                    # Fast exit: confident silence (~192 ms) or dead mic (~256 ms).
                    # Thresholds raised from 2/3 → 6/8 so a natural mid-sentence
                    # pause ("Hey JARVIS, [breath] open X") doesn't prematurely end
                    # capture before the user finishes speaking.
                    if speech_chunk_count >= min_speech_chunks and (
                        deep_silence_count >= 6    # ~192 ms of clear silence
                        or rms_quiet_count >= 8    # ~256 ms of quiet mic
                    ):
                        break

                    # Hard trailing timeout: no VAD-confirmed speech for 600 ms → done
                    if (
                        last_speech_time is not None
                        and speech_chunk_count >= min_speech_chunks
                        and (self.loop.time() - last_speech_time) >= _TRAILING_TIMEOUT_S
                    ):
                        logger.debug("Hard trailing timeout — ending capture")
                        break

                    # Normal exit: adaptive threshold (handles uncertain pauses)
                    needed = _silence_chunks_needed(elapsed_speech)
                    if silence_count >= needed:
                        break

        except asyncio.TimeoutError:
            logger.debug("Speech capture timeout")

        if not speech_started or speech_chunk_count < min_speech_chunks or not audio_buffer:
            return ""

        full_audio = np.concatenate(audio_buffer, axis=0).reshape(-1)
        if len(full_audio) < min_audio_samples:
            return ""

        # Let the UI show "transcribing" while Whisper processes — otherwise the
        # status stays "listening" for several seconds which looks like a hang.
        await self._publish_status("transcribing")
        _stt_start = self.loop.time()
        text = await self.stt.transcribe(full_audio)
        _stt_ms = int((self.loop.time() - _stt_start) * 1000)
        await self.event_bus.publish(
            RuntimeLogEvent("info", f"STT: {_stt_ms}ms ({len(full_audio) / 16000:.1f}s audio)")
        )
        if text:
            # Surface every transcription in the activity log so the user can
            # confirm that voice capture and STT are working, even when the
            # wake word wasn't detected or the phrase was filtered.
            await self.event_bus.publish(RuntimeLogEvent("info", f"Heard: {text}"))
        cleaned = extract_command_from_transcript(
            transcript=text,
            wake_phrase=self.config.voice.wake_word,
            require_wake_phrase=False,
        )
        logger.info(f"Captured: {cleaned or text!r}")
        return cleaned

    def _on_audio_level(self, level: float) -> None:
        if not self.loop:
            return
        now = self.loop.time()
        if now - self._last_meter_emit < 0.05:
            return
        self._last_meter_emit = now
        self._last_audio_level = level
        speech = self._last_speech_detected
        mode = self.mode if self.enabled else "disabled"

        def _publish():
            task = asyncio.create_task(
                self.event_bus.publish(
                    MicLevelEvent(level=level, speech_detected=speech, mode=mode)
                )
            )
            task.add_done_callback(
                lambda t: logger.debug(f"MicLevelEvent error: {t.exception()}")
                if not t.cancelled() and t.exception() else None
            )

        self.loop.call_soon_threadsafe(_publish)

    async def _publish_status(self, status: str) -> None:
        self._status = status
        await self.event_bus.publish(StatusEvent(status))

    def _effective_mode(self) -> str:
        """
        Mode determines if we need a wake word.
        'always_listening' transcribes everything.
        'wake_phrase' requires the name to be spoken.
        We respect the background_mode setting even when the window is visible.
        """
        return self.background_mode
