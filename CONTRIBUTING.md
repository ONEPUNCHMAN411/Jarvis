# Contributing

PRs are welcome. Here's how to get set up.

## Setup

```bash
git clone https://github.com/ONEPUNCHMAN411/Jarvis.git
cd Jarvis
pip install -e ".[dev]"
```

## Project layout

```
jarvis/brain/     AI providers, tools, memory, workflow engine
jarvis/control/   Computer control (screen, mouse, keyboard, accessibility)
jarvis/ui/        PyQt6 desktop UI
jarvis/voice/     STT, TTS, VAD, wake word
jarvis/plugins/   Plugin system
```

## Tests

```bash
python -m pytest tests/ -v
```

Some tests need hardware (mic, GPU) and are skipped in CI. That's fine, just don't break the ones that do run.

## Adding a provider

1. Create `jarvis/brain/your_provider.py` extending `LLMProvider`
2. Implement `chat()`, `stream_chat()`, and optionally `health_check()`
3. Register it in `jarvis/app.py` and add a card in `jarvis/ui/advanced_chat_window.py`

## Adding a plugin

1. Create `jarvis/plugins/your_plugin.py` extending `BasePlugin`
2. Implement `get_tools()` returning a list of `(ToolDefinition, Callable)` tuples
3. Register it in `jarvis/app.py` inside `_load_plugins()`

## Adding a tool

In `jarvis/brain/tools.py` inside `create_tool_registry()`:

```python
async def your_tool(param: str) -> str:
    """What this tool does (the AI reads this description)."""
    return "result"
```

Then add a `ToolDefinition` and register it.

## Style

- Python 3.12+ with type hints
- Async/await for anything that touches I/O
- Loguru for logging (`from loguru import logger`)
- Use try/except import guards for optional dependencies

## Build

```bash
python build_exe.py
# dist/JARVIS.exe
```

## Pull requests

Keep changes focused. One thing per PR. Add a test if the change is non-trivial. Run the test suite before submitting.

## License

MIT. All contributions go under the same license.
