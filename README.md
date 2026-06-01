<div align="center">

# JARVIS

Voice assistant for Windows 11. Talks back, controls your desktop, runs real browser automation, and routes to whatever AI provider you have configured.

[![Download](https://img.shields.io/badge/Download-v1-8B7CFF?style=for-the-badge&logo=windows)](https://github.com/ONEPUNCHMAN411/Jarvis/releases/latest)
[![Python](https://img.shields.io/badge/Python%203.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![MIT](https://img.shields.io/badge/MIT-10B981?style=for-the-badge)](LICENSE)

![JARVIS preview](assets/preview.png)

**[Download v1 for Windows 11](https://github.com/ONEPUNCHMAN411/Jarvis/releases/latest)**

</div>

---

## What you need

- Windows 11
- Python 3.12+
- 8 GB RAM (16 if you want local models) (GPU with at least 4 GB VRAM recommended)
- An API key for at least one provider (Groq is free, no card required)

---

## Install

Installer is ~1.8 GB. CUDA is bundled, that's why it's big.

**[JARVIS-Setup-v1.exe](https://github.com/ONEPUNCHMAN411/Jarvis/releases/latest)**

Or from source:

```bash
git clone https://github.com/ONEPUNCHMAN411/Jarvis.git
cd Jarvis
pip install -e .
python -m jarvis
```

First launch runs a setup wizard. Pick Groq, paste your key, done.

---

## What it does

- Talk to it, it talks back. Uses faster-whisper on CUDA, Edge TTS output, Silero VAD so it doesn't transcribe silence and fan noise
- Full desktop control: clicks, keyboard, drag-drop, screenshots, clipboard, app launcher, volume, brightness
- Playwright browser automation against real sites with JavaScript, not a scraping wrapper
- 50+ built-in tools covering web search, file management, system info, news
- Plugins for Gmail, Google Calendar, task scheduling, and more
- Switch providers live from the chat header, no restart needed
- Wake word detection if you install openwakeword (experimental, works fine with a decent USB mic but unreliable with a laptop mic)

---

## Providers

Start with Groq. It's free and the latency is good.

| Provider | Cost | Notes |
|----------|------|-------|
| Groq | Free tier | Llama 3.3 70B, fast |
| Gemini | Free tier | Google auth, no API key needed |
| Mistral | Pay per use | Solid at code |
| OpenAI | Pay per use | GPT-4o |
| Ollama | Free | Fully local, nothing sent out |
| OpenRouter | Pay per use | 50+ models in one place |

---

## How it works

Voice runs faster-whisper with Silero VAD gating it. Without VAD the STT model fires on silence and fan noise, latency adds up fast. With it, transcription only runs when someone's actually talking.

Computer control goes through the Windows UI Automation accessibility tree instead of pixel coordinates. Most LLMs can't see your screen, they need structured data about what's in each window. The accessibility tree gives that without needing a vision model. Vision is still available as a fallback if the tree doesn't expose what you need.

The orb is a raymarched GLSL sphere in a QOpenGLWidget. It was running at 60fps with 4x MSAA and 5 noise octaves, which ate GPU headroom the STT model needed. Dropped to 25fps, 2x MSAA, 3 octaves. Still looks the same, uses a fraction of the compute.

Provider routing tries your primary, falls back down a configured chain when the health check fails. So if Groq rate limits you it moves to the next provider instead of throwing an error.

---

## Config

Most settings live in the Settings panel inside the app. For the few things not exposed there, the base config is at `config/default.yaml` inside the install folder. The app also writes runtime settings to `%USERPROFILE%\.jarvis\settings.json`.

```yaml
# config/default.yaml - notable options
voice:
  stt_model: "tiny.en"     # medium.en is noticeably better, also noticeably slower
  wake_word: "hey jarvis"

ai:
  primary_provider: "groq"
  temperature: 0.7
```

---

## Keyboard shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+J` | Open JARVIS from anywhere |
| `Ctrl+K` | Command palette |
| `Ctrl+F` | Search chat |
| `Ctrl+Enter` | Send message |
| `↑` / `↓` | Input history |

---

## Local API

JARVIS exposes a local HTTP API on `localhost:8765` so you can drive it programmatically without touching the UI.

```bash
# Check if JARVIS is running and ready
curl http://localhost:8765/status

# Send a message (same as typing in the chat)
curl -s -X POST http://localhost:8765/chat \
     -H "Content-Type: application/json" \
     -d '{"text": "what time is it"}'

# Call a tool directly by name
curl -s -X POST http://localhost:8765/tool \
     -H "Content-Type: application/json" \
     -d '{"tool": "show_panel", "args": {"panel": "todo"}}'

# List all available tool names
curl http://localhost:8765/tools
```

The port can be changed in Settings → Advanced, or by editing `%USERPROFILE%\.jarvis\settings.json`:

```json
{ "local_api_port": 8766 }
```

---

## Build

```bash
python build_exe.py
# outputs dist/JARVIS.exe (~1.8 GB with CUDA)
```

---

## Credits

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper): CTranslate2 Whisper inference
- [Silero VAD](https://github.com/snakers4/silero-vad): voice activity detection
- [Playwright](https://playwright.dev): browser automation
- [pywinauto](https://github.com/pywinauto/pywinauto): Windows UI Automation
- [edge-tts](https://github.com/rany2/edge-tts): text to speech

---

MIT. Built for [Hack Club Stardance](https://stardance.hackclub.com) by Venkata.M.


