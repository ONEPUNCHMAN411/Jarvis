# Changelog

## [v1.1] - 2026-06-23

### Fixed
- Wake word sensitivity default raised to 0.6 - was cutting off short commands
- TTS speed reduced to +5% - default was slightly too fast for most Edge voices
- Memory window reduced to 40 messages - 50 was causing context overflow on long sessions
- Log retention bumped to 14 days

---
## [v1] - 2026-06-20

### Added
- Mute button next to Talk in the main view so you can mute without opening Settings
- Approval policy dropdown in the chat header (Ask / Auto-safe / Full auto)
- Working directory picker in Settings
- "Relaunch as Admin" button in Settings (opens UAC prompt)
- Wake word status now shows in Settings if openwakeword isn't installed, so it's obvious why it's not working instead of just being silent about it

### Fixed
- The orb was the main source of lag. Dropped it to 25fps, cut MSAA from 4x to 2x, reduced shader noise octaves from 5 to 3. Big improvement.
- Provider badge was being overwritten every status bar tick instead of showing the actual last-used provider
- Activity log showed raw provider IDs instead of readable names
- Default config was routing to the wrong provider when a different one was selected in the UI

### Changed
- Default provider is now Groq (fast, free tier, good latency)

---

## [1.0.0] - 2026-06-01

### Added
- Settings, AI panel, and Ollama model manager open as popout dialogs from the toolbar
- Guided API key setup for Groq, Mistral, OpenAI, Gemini, and OpenRouter. Click "Get API Key", browser opens the right signup page, paste and save
- Gemini can authenticate with a Google account instead of an API key
- Local model support via llama.cpp, including vision models
- Task scheduler plugin
- Workflow engine for multi-step AI tasks with checkpointing
- Python and shell code execution sandbox
- Screen reader for text-based providers that don't support vision

### Fixed
- App crashed in demo mode (`QLineEdit` doesn't have `setPlainText`)
- `KeyError` on startup when config was missing `automation_policy`
- MCP client crashed when writing to a disconnected server process
- Voice recovery task broke on Python 3.12 (the `get_event_loop` removal)
- Mic level callback was swallowing exceptions silently

### Changed
- Main window is 1100px wide now instead of 1680px, actually fits on a 1080p monitor
- Voice and llama.cpp load in background after the window opens so startup is fast

---

## [0.1.0] - 2026-05-14

First working version.

- Multi-LLM routing (Groq, Gemini, Mistral, OpenAI, OpenRouter, Ollama)
- Voice: faster-whisper with CUDA, Edge TTS, Silero VAD, wake word
- Computer control: screenshots, mouse, keyboard, clipboard, app launcher, Playwright
- 50+ tool registry
- Windows UI Automation via pywinauto
- System tray, command palette (Ctrl+K), chat search (Ctrl+F)
- Token budget indicator, message reactions, chat export
- 6-page setup wizard
- SQLite conversation history
- Plugins: Gmail, Google Calendar, Web Search, News, File Manager
- MCP tool bridge
