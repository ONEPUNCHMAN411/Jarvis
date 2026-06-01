import asyncio
import json
import os
import re
import signal
import sys
import time
import uuid
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication
from loguru import logger

from jarvis.brain.claude_code_provider import ClaudeCodeAutoProvider, ClaudeCodePipeProvider
from jarvis.brain.claude_provider import ClaudeProvider
from jarvis.brain.gemini_provider import GeminiProvider
from jarvis.brain.groq_provider import GroqProvider
from jarvis.brain.memory import ConversationMemory
from jarvis.brain.mistral_provider import MistralProvider
from jarvis.brain.ollama_provider import OllamaProvider
from jarvis.brain.openai_provider import OpenAIProvider
from jarvis.brain.openrouter_provider import OpenRouterProvider
from jarvis.brain.prompt_engine import PromptEngine
from jarvis.brain.provider_diagnostics import apply_settings_to_config, get_provider_help
from jarvis.brain.router import ProviderRouter
from jarvis.brain.strategy_memory import StrategyMemory
from jarvis.brain.tools import create_tool_registry
from jarvis.config import load_config
from jarvis.logger_config import setup_logging
from jarvis.models import (
    AIResponseEvent,
    Message,
    MicLevelEvent,
    PartialResponseEvent,
    ProactiveHelpEvent,
    RuntimeLogEvent,
    StatusEvent,
    ToolCallEvent,
    ToolResultEvent,
    TTSRequestEvent,
    UserSpeechEvent,
    UserTextEvent,
)
from jarvis.mcp.registry import MCPToolBridge
from jarvis.watcher.screen_watcher import ScreenWatcher
from jarvis.plugins.manager import PluginManager
from jarvis.runtime import AsyncRuntimeService
from jarvis.ui.advanced_chat_window import AdvancedChatWindow
from jarvis.ui.settings_store import SettingsStore

_MAX_TOOL_ROUNDS = 30


def _is_vision_capable(provider: str, model: str = "") -> bool:
    if provider.lower() in ("claude", "openai", "gemini"):
        return True
    if provider.lower() == "mistral" and "pixtral" in model.lower():
        return True
    if provider.lower() == "groq" and model.lower() in (
        "llama-3.2-90b-vision-preview", "llama-3.2-11b-vision-preview"
    ):
        return True
    if provider.lower() == "llamacpp" and model.lower() == "vision":
        # llamacpp with mmproj loaded — model sentinel set in _refresh_router
        return True
    return False

_MAX_TOOL_RESULT_CHARS = 4000
_TOOL_EXEC_TIMEOUT_S = 30.0

_runtime_instance = None

def get_runtime():
    """Return the running JarvisRuntime singleton, or None if not started yet."""
    return _runtime_instance

class AssistantBridge(QObject):
    event_received = pyqtSignal(object)

class JarvisRuntime:
    def __init__(self):
        self.bridge = AssistantBridge()
        self.async_runtime = AsyncRuntimeService()
        self.settings_store = SettingsStore()
        self.settings = self.settings_store.load()
        self.config = apply_settings_to_config(load_config(), self.settings)
        self.automation_policy = self.settings.get("automation_policy", "full_auto")

        self.ready = False
        self.plugin_manager = None
        self.tool_registry = None
        self.provider_router = None
        self.prompt_engine = None
        self.memory = None
        self.strategy_memory = None
        self.voice_manager = None
        self.services = None
        self._initialization_future = None
        self._idle_safety_task: asyncio.Task | None = None
        self._cached_tool_definitions: list[dict] | None = None
        self.mcp_bridge: MCPToolBridge | None = None
        self.screen_watcher: ScreenWatcher | None = None
        self._local_api: "LocalAPIServer | None" = None
        self._llamacpp_launcher = None
        self._live_transcription = None
        self._pending_approvals: dict[str, asyncio.Future] = {}
        self._always_approved: set[str] = set()

    async def _approval_callback(self, action_name: str, risk: str) -> bool:
        """Called from async tool thread when a 'confirm'-risk action needs approval."""
        if action_name in self._always_approved:
            return True
        approval_id = str(uuid.uuid4())[:8]
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending_approvals[approval_id] = (future, action_name)
        self._emit_ui_event({
            "type": "approval_request",
            "id": approval_id,
            "action": action_name,
            "risk": risk,
        })
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=120)
        except asyncio.TimeoutError:
            self._pending_approvals.pop(approval_id, None)
            return False

    def approve_action(self, approval_id: str, always: bool = False) -> None:
        """Called from the Qt UI thread when the user clicks Approve."""
        entry = self._pending_approvals.pop(approval_id, None)
        if entry is None:
            return
        future, action_name = entry
        if always:
            self._always_approved.add(action_name)
        loop = self.async_runtime.loop
        if loop and not loop.is_closed():
            loop.call_soon_threadsafe(future.set_result, True)

    def decline_action(self, approval_id: str) -> None:
        """Called from the Qt UI thread when the user clicks Decline."""
        entry = self._pending_approvals.pop(approval_id, None)
        if entry is None:
            return
        future, _ = entry
        loop = self.async_runtime.loop
        if loop and not loop.is_closed():
            loop.call_soon_threadsafe(future.set_result, False)

    def start(self) -> None:
        self.async_runtime.start()
        self._initialization_future = self.async_runtime.submit(self._async_initialize())
        self._emit_ui_event(
            {
                "type": "log",
                "level": "info",
                "message": "Starting JARVIS runtime",
            }
        )

    def stop(self) -> None:
        try:
            if self.ready:
                self.async_runtime.submit(self._async_shutdown()).result(timeout=15)
        finally:
            self.async_runtime.stop()

    def send_text(self, text: str) -> None:
        if not text.strip():
            return
        self._emit_ui_event(
            {
                "type": "message",
                "sender": "YOU",
                "text": text,
                "origin": "typed",
            }
        )
        self.async_runtime.submit(self.async_runtime.bus.publish(UserTextEvent(text=text)))

    def apply_settings(self, settings: dict) -> None:
        self.settings_store.save(settings)
        self.settings = settings
        self.config = apply_settings_to_config(self.config, settings)
        self.automation_policy = settings.get("automation_policy", "full_auto")
        self._emit_ui_event({"type": "settings_saved", "settings": settings})
        self.async_runtime.submit(self._async_apply_settings(settings))

    def test_provider(self, provider_name: str) -> None:
        self.async_runtime.submit(self._async_test_provider(provider_name))

    def preview_voice(self, profile_id: str, custom_profile: dict | None = None) -> None:
        self.async_runtime.submit(self._async_preview_voice(profile_id, custom_profile))

    def set_background_state(self, backgrounded: bool) -> None:
        self.async_runtime.submit(self._async_set_background_state(backgrounded))

    def list_plugins(self) -> None:
        self.async_runtime.submit(self._async_list_plugins())

    def enable_plugin(self, name: str) -> None:
        self.async_runtime.submit(self._async_set_plugin_enabled(name, True))

    def disable_plugin(self, name: str) -> None:
        self.async_runtime.submit(self._async_set_plugin_enabled(name, False))

    def get_status(self) -> None:
        import psutil
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        providers = list(self.provider_router._providers.keys()) if self.provider_router else []
        self._emit_ui_event({
            "type": "status_report",
            "cpu": cpu,
            "mem_pct": mem.percent,
            "providers": providers,
            "voice_enabled": self.settings.get("voice_enabled", True),
            "plugins": [p for p in self.plugin_manager.plugins] if self.plugin_manager else [],
        })

    async def _async_list_plugins(self) -> None:
        if not self.plugin_manager:
            self._emit_ui_event({"type": "plugins_list", "plugins": []})
            return
        plugins = [
            {"name": p.name, "enabled": p.enabled}
            for p in self.plugin_manager.plugins.values()
        ]
        self._emit_ui_event({"type": "plugins_list", "plugins": plugins})

    async def _async_set_plugin_enabled(self, name: str, enabled: bool) -> None:
        if not self.plugin_manager or name not in self.plugin_manager.plugins:
            self._emit_ui_event({
                "type": "log", "level": "warning",
                "message": f"Plugin '{name}' not found",
            })
            return
        plugin = self.plugin_manager.plugins[name]
        plugin.enabled = enabled
        state = "enabled" if enabled else "disabled"
        await self.async_runtime.bus.publish(RuntimeLogEvent("info", f"Plugin '{name}' {state}"))
        self._emit_ui_event({
            "type": "log", "level": "info",
            "message": f"Plugin '{name}' {state}",
        })
        # Refresh plugins list so UI updates
        await self._async_list_plugins()

    async def _async_initialize(self) -> None:
        self.plugin_manager = PluginManager()
        self.memory = ConversationMemory(str(Path.home() / ".jarvis" / "conversation_memory.db"))
        await self.memory.initialize()
        self.strategy_memory = StrategyMemory()

        self.services = self._build_services()
        self.services["_runtime"] = self  # gives tools access to live transcription service
        self.tool_registry = create_tool_registry(
            services=self.services,
            policy_provider=lambda: self.automation_policy,
            approval_callback=self._approval_callback,
        )
        await self._load_plugins()

        self.mcp_bridge = MCPToolBridge(self.tool_registry)
        mcp_servers = self.config.mcp.servers
        for srv in mcp_servers:
            if not srv.get("enabled", True):
                continue
            try:
                count = await self.mcp_bridge.register_server(srv)
                logger.info(f"MCP server '{srv['name']}': {count} tools registered")
            except Exception as e:
                logger.warning(f"MCP server '{srv.get('name', '?')}' failed: {e}")
        if mcp_servers:
            self._cached_tool_definitions = None

        # Start llama-server BEFORE building the router so the health check passes
        # on the first request (model loading can take 10-60s on slow machines).
        await self._start_llamacpp_if_configured()

        await self._refresh_router()
        self.prompt_engine = PromptEngine(self.config, self.tool_registry)

        _claude_key = self.config.ai.providers.get("claude", {}).get("api_key") or ""
        if not _claude_key:
            import os as _os
            _claude_key = _os.environ.get("ANTHROPIC_API_KEY", "")
        if _claude_key and self.memory:
            from anthropic import AsyncAnthropic as _AsyncAnthropic
            self.memory.set_ai_client(_AsyncAnthropic(api_key=_claude_key))

        self.async_runtime.bus.subscribe(UserTextEvent, self._handle_user_input)
        self.async_runtime.bus.subscribe(UserSpeechEvent, self._handle_user_input)
        self.async_runtime.bus.subscribe(UserSpeechEvent, self._mirror_user_speech)
        self.async_runtime.bus.subscribe(AIResponseEvent, self._mirror_ai_response)
        self.async_runtime.bus.subscribe(PartialResponseEvent, self._mirror_partial_response)
        self.async_runtime.bus.subscribe(StatusEvent, self._mirror_status)
        self.async_runtime.bus.subscribe(MicLevelEvent, self._mirror_mic)
        self.async_runtime.bus.subscribe(RuntimeLogEvent, self._mirror_log)
        self.async_runtime.bus.subscribe(ToolCallEvent, self._mirror_tool_call)
        self.async_runtime.bus.subscribe(ToolResultEvent, self._mirror_tool_result)
        self.async_runtime.bus.subscribe(ProactiveHelpEvent, self._mirror_proactive_help)

        from jarvis.models import TranscriptionChunkEvent
        from jarvis.voice.live_transcription import LiveTranscriptionService
        self._live_transcription = LiveTranscriptionService(self.async_runtime.bus)
        self.async_runtime.bus.subscribe(TranscriptionChunkEvent, self._mirror_transcription_chunk)

        try:
            from jarvis.voice.voice_manager import VoiceManager
            self.voice_manager = VoiceManager(
                self.async_runtime.bus,
                self.config,
                voice_profile_id=self.settings.get("voice_profile", "jarvis"),
                custom_voice_profile=self.settings.get("custom_voice_profile"),
            )
            await self.voice_manager.initialize()
            await self.voice_manager.set_mode(self.settings.get("background_mode", "wake_phrase"))
        except Exception as _ve:
            logger.warning(f"Voice system failed to initialize: {_ve} — running without voice")
            self.voice_manager = None
            self._emit_ui_event({
                "type": "log", "level": "warning",
                "message": f"Voice unavailable: {_ve}",
            })

        watcher_cfg = self.config.watcher.model_dump() if hasattr(self.config, "watcher") else {}
        if self.services and self.provider_router:
            self.screen_watcher = ScreenWatcher(
                bus=self.async_runtime.bus,
                screen_service=self.services.get("screen"),
                provider_router=self.provider_router,
                config=watcher_cfg,
            )
            if watcher_cfg.get("enabled", False):
                self.screen_watcher.start()

        self.ready = True
        await self.async_runtime.bus.publish(RuntimeLogEvent("info", "JARVIS runtime ready"))
        self._emit_ui_event({"type": "settings_loaded", "settings": self.settings})
        self._emit_ui_event({"type": "runtime_ready"})

        # Start headless API server so panels/tools can be driven without the Qt UI
        try:
            from jarvis.api.local_server import LocalAPIServer
            port = self.settings.get("local_api_port", 8765)
            self._local_api = LocalAPIServer(self, port=port)
            await self._local_api.start()
        except OSError as _api_exc:
            logger.error(
                f"Local API server could not bind to port {self.settings.get('local_api_port', 8765)} "
                f"— port may already be in use. Set 'local_api_port' in ~/.jarvis/settings.json to use a different port. ({_api_exc})"
            )
        except Exception as _api_exc:
            logger.warning(f"Local API server failed to start: {_api_exc}")

    async def _start_llamacpp_if_configured(self) -> None:
        """Start llama-server subprocess if llamacpp provider is enabled and has a model path."""
        llamacpp_cfg = self.config.ai.providers.get("llamacpp", {})
        if not llamacpp_cfg.get("enabled") or not llamacpp_cfg.get("model_path"):
            return
        # Pass ALL keys from config so reasoning/thinking control, parallel slots, prio,
        # spec type, KV types etc. are all honoured — not just a hardcoded subset.
        from jarvis.utils.llamacpp_launcher import DEFAULT_CONFIG as _LC_DEFAULTS
        launcher_config = dict(_LC_DEFAULTS)  # start from launcher defaults
        # Override with every key present in the YAML config
        for key in _LC_DEFAULTS:
            if key in llamacpp_cfg:
                launcher_config[key] = llamacpp_cfg[key]
        # Always keep model_path from config (required)
        launcher_config["model_path"] = llamacpp_cfg["model_path"]
        from jarvis.utils.llamacpp_launcher import LlamaCppLauncher
        self._llamacpp_launcher = LlamaCppLauncher(launcher_config)
        ok = await self._llamacpp_launcher.start()
        if ok:
            _has_vision = bool(llamacpp_cfg.get("mmproj_path"))
            _mode = "vision + text" if _has_vision else "text only"
            await self.async_runtime.bus.publish(
                RuntimeLogEvent("info", f"llama-server started (local AI — {_mode})")
            )
        else:
            await self.async_runtime.bus.publish(
                RuntimeLogEvent("warning", "llama-server failed to start — check data/llamacpp.log")
            )

    async def _async_shutdown(self) -> None:
        self.ready = False
        if self._local_api:
            await self._local_api.stop()
        if self.screen_watcher:
            self.screen_watcher.stop()
        if self._llamacpp_launcher:
            await self._llamacpp_launcher.stop()
        if self.voice_manager:
            await self.voice_manager.shutdown()
        if self.mcp_bridge:
            await self.mcp_bridge.shutdown()
        if self.plugin_manager:
            await self.plugin_manager.shutdown_all()
        if self.memory:
            await self.memory.save_to_db()

    async def _async_apply_settings(self, settings: dict) -> None:
        prev_settings = self.settings
        self.settings = settings
        self.automation_policy = settings.get("automation_policy", "full_auto")
        self.config = apply_settings_to_config(load_config(), settings)

        # Restart llama-server if model_path or enabled state changed
        prev_llamacpp = (prev_settings or {}).get("providers", {}).get("llamacpp", {})
        new_llamacpp  = settings.get("providers", {}).get("llamacpp", {})
        _llamacpp_changed = (
            prev_llamacpp.get("model_path") != new_llamacpp.get("model_path")
            or prev_llamacpp.get("enabled") != new_llamacpp.get("enabled")
            or prev_llamacpp.get("port") != new_llamacpp.get("port")
        )
        if _llamacpp_changed:
            # Stop old server (if any)
            if self._llamacpp_launcher:
                await self._llamacpp_launcher.stop()
                self._llamacpp_launcher = None
            # Start new server with fresh config
            await self._start_llamacpp_if_configured()

        await self._refresh_router()

        if self.voice_manager:
            await self.voice_manager.set_enabled(bool(settings.get("voice_enabled", True)))
            await self.voice_manager.set_mode(settings.get("background_mode", "wake_phrase"))
            await self.voice_manager.set_voice_profile(
                settings.get("voice_profile", "jarvis"),
                settings.get("custom_voice_profile"),
            )

            new_sensitivity = settings.get("wake_word_sensitivity")
            if new_sensitivity is not None and new_sensitivity != prev_settings.get("wake_word_sensitivity"):
                await self.voice_manager.set_wake_word_sensitivity(float(new_sensitivity))

            new_model = settings.get("stt_model")
            new_lang = settings.get("stt_language", "en")
            if new_model and (
                new_model != prev_settings.get("stt_model")
                or new_lang != prev_settings.get("stt_language", "en")
            ):
                await self.voice_manager.reload_stt(new_model, new_lang)

            new_device = settings.get("input_device")
            if new_device != prev_settings.get("input_device"):
                await self.voice_manager.set_input_device(new_device)

        self._emit_ui_event({"type": "settings_loaded", "settings": self.settings})

    def load_chat_history(self) -> None:
        self.async_runtime.submit(self._async_load_chat_history())

    async def _async_load_chat_history(self) -> None:
        if not self.memory:
            return
        try:
            # Load the most recent session from DB on first startup
            sessions = await self.memory.list_sessions(limit=1)
            if sessions and not self.memory._messages:
                await self.memory.load_from_db(sessions[0]["session_id"])
            messages = self.memory.get_context(max_tokens=32000)
            history = [
                {"role": m.role, "content": m.content}
                for m in messages
                if m.role in ("user", "assistant") and m.content.strip()
            ]
            self._emit_ui_event({
                "type": "chat_history",
                "messages": history,
                "session_id": self.memory.session_id,
            })
        except Exception as exc:
            logger.warning(f"Failed to load chat history: {exc}")

    def new_chat_session(self) -> None:
        """Save current session and start a fresh one."""
        self.async_runtime.submit(self._async_new_session())

    async def _async_new_session(self) -> None:
        if not self.memory:
            return
        new_sid = await self.memory.new_session()
        self._cached_tool_definitions = None
        self._emit_ui_event({"type": "new_session", "session_id": new_sid})

    def list_chat_sessions(self) -> None:
        self.async_runtime.submit(self._async_list_sessions())

    async def _async_list_sessions(self) -> None:
        if not self.memory:
            return
        sessions = await self.memory.list_sessions(limit=100)
        self._emit_ui_event({"type": "session_list", "sessions": sessions})

    def load_session(self, session_id: str) -> None:
        self.async_runtime.submit(self._async_load_session(session_id))

    async def _async_load_session(self, session_id: str) -> None:
        if not self.memory:
            return
        await self.memory.load_from_db(session_id)
        messages = self.memory.get_context(max_tokens=32000)
        history = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant") and m.content.strip()
        ]
        self._emit_ui_event({
            "type": "chat_history",
            "messages": history,
            "session_id": session_id,
        })

    async def _async_preview_voice(self, profile_id: str, custom_profile: dict | None = None) -> None:
        if not self.voice_manager:
            return
        await self.voice_manager.set_voice_profile(profile_id, custom_profile)
        await self.voice_manager.preview_voice()

    async def _async_set_background_state(self, backgrounded: bool) -> None:
        if not self.voice_manager:
            return
        await self.voice_manager.set_backgrounded(backgrounded)

    async def _async_test_provider(self, provider_name: str) -> None:
        await self._refresh_router()
        help_info = get_provider_help(provider_name)
        provider = self.provider_router._providers.get(provider_name) if self.provider_router else None

        if provider is None:
            self._emit_ui_event(
                {
                    "type": "provider_test",
                    "provider": provider_name,
                    "success": False,
                    "message": "Provider is not enabled or not configured.",
                    "help": help_info,
                }
            )
            return

        try:
            healthy = await provider.health_check()
            self._emit_ui_event(
                {
                    "type": "provider_test",
                    "provider": provider_name,
                    "success": healthy,
                    "message": "Provider responded successfully." if healthy else "Provider health check failed.",
                    "help": help_info,
                }
            )
        except Exception as exc:
            self._emit_ui_event(
                {
                    "type": "provider_test",
                    "provider": provider_name,
                    "success": False,
                    "message": str(exc),
                    "help": help_info,
                }
            )

    async def _load_plugins(self) -> None:
        import importlib
        import inspect
        import pkgutil
        import jarvis.plugins as _pkg
        from jarvis.plugins.base import Plugin

        for importer, modname, ispkg in pkgutil.iter_modules(_pkg.__path__):
            if not modname.endswith("_plugin"):
                continue
            try:
                mod = importlib.import_module(f"jarvis.plugins.{modname}")
            except Exception as exc:
                await self.async_runtime.bus.publish(
                    RuntimeLogEvent("warning", f"Plugin module {modname} import failed: {exc}")
                )
                continue
            for _name, obj in inspect.getmembers(mod, inspect.isclass):
                if not issubclass(obj, Plugin) or obj is Plugin:
                    continue
                if obj.__module__ != mod.__name__:
                    continue  # skip re-exported base classes
                try:
                    plugin = obj()
                    await self.plugin_manager.register_plugin(plugin)
                    for definition, handler in plugin.get_tools():
                        self.tool_registry.register(definition, handler)
                    await self.async_runtime.bus.publish(
                        RuntimeLogEvent(
                            "info",
                            f"Loaded plugin {plugin.name} with {len(plugin.get_tools())} tools",
                        )
                    )
                except Exception as exc:
                    await self.async_runtime.bus.publish(
                        RuntimeLogEvent("warning", f"Plugin {modname}/{_name} failed: {exc}")
                    )

    async def _refresh_router(self) -> None:
        providers = {}
        provider_settings = self.config.ai.providers

        cc_cfg = provider_settings.get("claude_code", {})
        cc_mode = cc_cfg.get("mode", "auto")
        if cc_mode in ("auto", "both"):
            providers["claude_code_auto"] = ClaudeCodeAutoProvider()
        if cc_mode in ("pipe", "both"):
            providers["claude_code_pipe"] = ClaudeCodePipeProvider()

        ollama_cfg = provider_settings.get("ollama", {})
        if ollama_cfg.get("enabled", True):
            providers["ollama"] = OllamaProvider(
                model=ollama_cfg.get("model", "llama3.1:8b"),
                coding_model=ollama_cfg.get("coding_model", "qwen2.5:7b"),
                base_url=ollama_cfg.get("base_url", "http://localhost:11434"),
                timeout=ollama_cfg.get("timeout", 30),
            )

        groq_cfg = provider_settings.get("groq", {})
        if groq_cfg.get("enabled") and groq_cfg.get("api_key"):
            providers["groq"] = GroqProvider(
                api_key=groq_cfg["api_key"],
                model=groq_cfg.get("model", "llama-3.3-70b-versatile"),
            )

        gemini_cfg = provider_settings.get("gemini", {})
        _gemini_api_key = gemini_cfg.get("api_key", "")
        _gemini_oauth = gemini_cfg.get("oauth_token_path", "")
        if gemini_cfg.get("enabled") and (_gemini_api_key or _gemini_oauth):
            providers["gemini"] = GeminiProvider(
                api_key=_gemini_api_key,
                model=gemini_cfg.get("model", "gemini-2.0-flash"),
                oauth_token_path=_gemini_oauth or None,
            )

        openrouter_cfg = provider_settings.get("openrouter", {})
        if openrouter_cfg.get("enabled") and openrouter_cfg.get("api_key"):
            providers["openrouter"] = OpenRouterProvider(
                api_key=openrouter_cfg["api_key"],
                model=openrouter_cfg.get("model", "meta-llama/llama-3.1-8b-instruct:free"),
            )

        claude_cfg = provider_settings.get("claude", {})
        if claude_cfg.get("enabled") and claude_cfg.get("api_key"):
            providers["claude"] = ClaudeProvider(
                api_key=claude_cfg["api_key"],
                model=claude_cfg.get("model", "claude-haiku-4-5"),
            )

        openai_cfg = provider_settings.get("openai", {})
        if openai_cfg.get("enabled") and openai_cfg.get("api_key"):
            providers["openai"] = OpenAIProvider(
                api_key=openai_cfg["api_key"],
                model=openai_cfg.get("model", "gpt-4o"),
                base_url=openai_cfg.get("base_url"),
            )

        mistral_cfg = provider_settings.get("mistral", {})
        if mistral_cfg.get("enabled") and mistral_cfg.get("api_key"):
            providers["mistral"] = MistralProvider(
                api_key=mistral_cfg["api_key"],
                model=mistral_cfg.get("model", "mistral-small-latest"),
            )

        llamacpp_cfg = provider_settings.get("llamacpp", {})
        if llamacpp_cfg.get("enabled") and llamacpp_cfg.get("model_path"):
            _mmproj = llamacpp_cfg.get("mmproj_path", "")
            from jarvis.brain.llamacpp_provider import LlamaCppProvider
            providers["llamacpp"] = LlamaCppProvider(
                base_url=llamacpp_cfg.get("base_url", "http://127.0.0.1:8080/v1"),
                # Use "vision" sentinel so _is_vision_capable can detect it
                model="vision" if _mmproj else "local",
                has_mmproj=bool(_mmproj),
            )

        fallback = list(self.config.ai.fallback_order)
        order = [name for name in fallback if name in providers]
        for name in providers:
            if name not in order:
                order.append(name)
        logger.info("AI provider instances active: {}", list(providers.keys()))
        self.provider_router = ProviderRouter(providers, order)

    def _build_services(self) -> dict:
        from jarvis.control.accessibility import AccessibilityReader
        from jarvis.control.app_launcher import AppLauncher
        from jarvis.control.browser import Browser
        from jarvis.control.clipboard import Clipboard
        from jarvis.control.keyboard import Keyboard
        from jarvis.control.mouse import Mouse
        from jarvis.control.screen import Screen
        from jarvis.control.system import SystemControl
        from jarvis.control.window import WindowControl

        return {
            "screen": Screen(screenshot_dir=str(Path.home() / ".jarvis" / "screenshots")),
            "clipboard": Clipboard(),
            "browser": Browser(headless=False),
            "apps": AppLauncher(),
            "keyboard": Keyboard(),
            "mouse": Mouse(),
            "system": SystemControl(),
            "window": WindowControl(),
            "accessibility": AccessibilityReader(),
        }

    def _effective_primary_provider(self) -> str:
        """Resolve UI primary selection; when UI is 'auto', honor YAML ai.primary_provider."""
        sp = self.settings.get("primary_provider", "auto")
        if sp != "auto":
            return sp
        cp = getattr(self.config.ai, "primary_provider", None) or ""
        cp_norm = str(cp).strip().lower()
        if cp_norm and cp_norm != "auto":
            return str(cp).strip()
        return "auto"

    def _get_provider_model(self, provider_name: str | None) -> str:
        """Return the configured model string for a given provider."""
        if not provider_name or not self.provider_router:
            return ""
        prov = self.provider_router._providers.get(provider_name)
        if prov and hasattr(prov, "model"):
            return str(prov.model)
        return ""

    async def _generate_screen_description(self) -> str:
        """Build a text description of the visible screen for non-vision providers.

        Uses Moondream (local vision) first for accurate visual understanding,
        then falls back to accessibility text if Moondream is unavailable.
        """
        # PRIMARY: Moondream local vision — actual visual understanding of the screen
        try:
            from jarvis.brain.local_vision import get_local_vision
            lv = get_local_vision()
            if lv.ready:
                desc = await asyncio.to_thread(
                    lv.describe_screen,
                    "Describe what you see on this screen: the active application, "
                    "visible text content, UI controls, and what the user appears to be doing."
                )
                if desc and len(desc) > 20:
                    return f"[Visual screen description]: {desc}"
        except Exception:
            pass

        # FALLBACK: text-based accessibility tree
        try:
            from jarvis.control.screen_reader import ScreenReader
            reader = ScreenReader()
            desc = await reader.describe_screen(max_elements=30)
            if desc and len(desc) > 30:
                return desc
        except Exception:
            pass

        # LAST RESORT: raw accessibility service
        parts: list[str] = []
        try:
            acc = self.services.get("accessibility")
            if acc and hasattr(acc, "get_window_elements"):
                elements = await acc.get_window_elements(title="", max_elements=30)
                el_strs = []
                for el in (elements or []):
                    if not isinstance(el, dict) or "error" in el:
                        continue
                    name = el.get("name", "").strip()
                    ctrl_type = el.get("type", el.get("role", "")).strip()
                    bounds = el.get("bounds", el.get("rect", {}))
                    if name and ctrl_type:
                        cx = bounds.get("x", 0) + bounds.get("w", bounds.get("width", 0)) // 2
                        cy = bounds.get("y", 0) + bounds.get("h", bounds.get("height", 0)) // 2
                        el_strs.append(f"  [{ctrl_type}] {name} at ({cx},{cy})")
                if el_strs:
                    parts.append("Visible UI elements:\n" + "\n".join(el_strs))
        except Exception:
            pass

        return "\n".join(parts) if parts else ""

    async def _handle_user_input(self, event: UserTextEvent | UserSpeechEvent) -> None:  # noqa: C901
        try:
            if self.voice_manager:
                await self.voice_manager.set_processing(True)

            if not self.provider_router:
                await self.async_runtime.bus.publish(
                    AIResponseEvent(
                        text="JARVIS is still initializing. Wait a few seconds and try again.",
                    )
                )
                return

            user_text = event.text.strip()
            from jarvis.voice.utterance import is_meaningful_transcript
            if not user_text or not is_meaningful_transcript(user_text):
                return

            await self.async_runtime.bus.publish(StatusEvent("thinking"))
            primary = self._effective_primary_provider()
            await self.async_runtime.bus.publish(
                RuntimeLogEvent(
                    "info",
                    f"Request received — primary={primary!r}, routing to AI provider",
                )
            )
            category = self._categorize_request(user_text)
            if primary != "auto":
                preferred_provider = primary
            else:
                preferred = self.strategy_memory.pick(
                    category=category,
                    available_providers=list(self.provider_router._providers.keys()),
                )
                preferred_provider = preferred["provider"] if preferred else None

            prompt_text = user_text
            _proactive_screenshot: str | None = None
            if self.settings.get("screen_awareness", True) and self._should_capture_screen(user_text):
                try:
                    _proactive_screenshot = await self.services["screen"].take_screenshot()
                    # Keep a short text hint for providers that don't support vision
                    prompt_text += f"\n\n[Screenshot captured: {_proactive_screenshot}]"
                    await self.async_runtime.bus.publish(
                        RuntimeLogEvent("info", f"Captured screen context: {_proactive_screenshot}")
                    )
                except Exception as exc:
                    await self.async_runtime.bus.publish(
                        RuntimeLogEvent("warning", f"Screen capture failed: {exc}")
                    )

            _active_model = self._get_provider_model(preferred_provider)
            messages = self.memory.get_context_with_summary(
                max_tokens=8000, summary_threshold=40
            )
            # Build user message — embed screenshot only for vision-capable providers
            _user_msg = Message(role="user", content=prompt_text)
            _req_vision_ok = _is_vision_capable(preferred_provider or "", _active_model)
            if _proactive_screenshot and _req_vision_ok:
                _user_msg.image_paths = [_proactive_screenshot]
            elif _proactive_screenshot and not _req_vision_ok:
                # Non-vision provider: append a text description of the screen
                try:
                    _desc = await self._generate_screen_description()
                    if _desc:
                        _user_msg.content += f"\n\n[Screen description: {_desc}]"
                except Exception:
                    pass
            messages.append(_user_msg)

            display_hint = ""
            if self.settings.get("screen_awareness", True) and self.services:
                try:
                    display_hint = self.services["screen"].get_automation_display_hint()
                except Exception:
                    display_hint = ""

            pinned_context = self.settings.get("pinned_context", "").strip()
            system_prompt = self.prompt_engine.build(
                automation_policy=self.automation_policy,
                screen_awareness=self.settings.get("screen_awareness", True),
                preferred_provider=preferred_provider,
                preferred_model=_active_model,
                display_hint=display_hint or None,
                category=category,
                pinned_context=pinned_context or None,
            )

            if self._cached_tool_definitions is None:
                self._cached_tool_definitions = self.tool_registry.get_definitions()
            tool_definitions = self._cached_tool_definitions

            _stream_accumulated = ""

            async def _on_stream_chunk(delta: str):
                nonlocal _stream_accumulated
                _stream_accumulated += delta
                await self.async_runtime.bus.publish(
                    PartialResponseEvent(delta=delta, accumulated=_stream_accumulated)
                )

            async def _llm_chat(with_tools: bool):
                nonlocal _stream_accumulated
                _stream_accumulated = ""
                return await self.provider_router.stream_chat(
                    messages,
                    tools=tool_definitions if with_tools else None,
                    system_prompt=system_prompt,
                    temperature=self.config.ai.temperature,
                    preferred_provider=preferred_provider,
                    category=category,
                    on_chunk=_on_stream_chunk,
                )

            # GPU-contention guard
            # Local GPU providers (Ollama, llamacpp) hold the CUDA device during
            # inference.  Whisper (ctranslate2) also wants CUDA for transcription.
            # Signal STT to use its CPU fallback model while the LLM is running so
            # the two backends never compete for the same CUDA kernels.
            _gpu_providers = {"ollama", "llamacpp"}
            _using_local_gpu = (preferred_provider or "").lower() in _gpu_providers
            if _using_local_gpu and self.voice_manager:
                self.voice_manager.set_gpu_busy(True)

            try:
                response = await _llm_chat(True)
            except Exception as first_err:
                err_str = str(first_err)
                if "tool_use_failed" in err_str or "failed_generation" in err_str:
                    logger.warning("Tool use failed, retrying without tools")
                    await self.async_runtime.bus.publish(
                        RuntimeLogEvent("warning", "Tool call failed — retrying as plain chat")
                    )
                    response = await _llm_chat(False)
                else:
                    raise
            finally:
                # Always release the GPU — even if inference threw an exception.
                if _using_local_gpu and self.voice_manager:
                    self.voice_manager.set_gpu_busy(False)

            tool_names: list[str] = []

            for _round in range(_MAX_TOOL_ROUNDS):
                if not response.tool_calls:
                    break

                await self.async_runtime.bus.publish(
                    RuntimeLogEvent("info", f"Step {_round + 1}: executing {len(response.tool_calls)} tool(s)")
                )

                messages.append(
                    Message(
                        role="assistant",
                        content=response.text or "",
                        tool_calls=[
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {"name": tc.name, "arguments": json.dumps(tc.args)},
                            }
                            for tc in response.tool_calls
                        ],
                    )
                )
                _active_provider = response.provider or preferred_provider or ""
                _active_model_str = self._get_provider_model(_active_provider)
                _vision_ok = _is_vision_capable(_active_provider, _active_model_str)

                for tool_call in response.tool_calls:
                    tool_names.append(tool_call.name)
                    await self.async_runtime.bus.publish(
                        ToolCallEvent(tool_call.name, tool_call.args, tool_call.id)
                    )
                    try:
                        # Check LRU cache before executing (skips time-sensitive tools)
                        _cached = self.memory.get_cached_tool_result(tool_call.name, tool_call.args)
                        if _cached is not None:
                            result = _cached
                        else:
                            result = await asyncio.wait_for(
                                self.tool_registry.execute(tool_call.name, tool_call.args),
                                timeout=_TOOL_EXEC_TIMEOUT_S,
                            )
                            self.memory.cache_tool_result(tool_call.name, tool_call.args, str(result))
                        await self.async_runtime.bus.publish(
                            ToolResultEvent(tool_call.id, tool_call.name, result, True)
                        )
                        result_str = str(result)
                        # Cap large results so local/Groq models don't OOM
                        if len(result_str) > _MAX_TOOL_RESULT_CHARS:
                            result_str = result_str[:_MAX_TOOL_RESULT_CHARS] + "\n… [output truncated]"
                        tool_msg = Message(
                            role="tool",
                            content=f"{tool_call.name} result: {result_str}",
                            tool_call_id=tool_call.id,
                        )
                        # Handle screenshot results based on provider vision capability
                        if isinstance(result, str) and ".png" in result:
                            _png = None
                            if result.endswith(".png") and os.path.exists(result):
                                _png = result
                            else:
                                _m = re.search(r'([^\s"\']+\.png)', result)
                                if _m and os.path.exists(_m.group(1)):
                                    _png = _m.group(1)
                            if _png and _vision_ok:
                                # Vision model: embed screenshot as image
                                tool_msg.image_paths = [_png]
                            elif _png and not _vision_ok:
                                # Non-vision model: describe screenshot with Moondream
                                try:
                                    from jarvis.brain.local_vision import get_local_vision
                                    _lv = get_local_vision()
                                    if _lv.ready:
                                        _vis_desc = await asyncio.to_thread(
                                            _lv.describe,
                                            _png,
                                            "Describe this screenshot in detail: active application, "
                                            "visible text, UI controls, and what the user is doing."
                                        )
                                        if _vis_desc:
                                            tool_msg.content = (
                                                f"{tool_call.name} result: [Screenshot described by Moondream] "
                                                f"{_vis_desc}"
                                            )
                                except Exception:
                                    pass
                        messages.append(tool_msg)
                    except asyncio.TimeoutError:
                        err_msg = f"{tool_call.name} timed out after {_TOOL_EXEC_TIMEOUT_S:.0f}s"
                        await self.async_runtime.bus.publish(
                            ToolResultEvent(tool_call.id, tool_call.name, err_msg, False)
                        )
                        messages.append(
                            Message(
                                role="tool",
                                content=err_msg,
                                tool_call_id=tool_call.id,
                            )
                        )
                    except Exception as exc:
                        await self.async_runtime.bus.publish(
                            ToolResultEvent(tool_call.id, tool_call.name, str(exc), False)
                        )
                        messages.append(
                            Message(
                                role="tool",
                                content=f"{tool_call.name} failed: {exc}",
                                tool_call_id=tool_call.id,
                            )
                        )

                # Re-acquire GPU guard for each follow-up LLM call in tool loop
                if _using_local_gpu and self.voice_manager:
                    self.voice_manager.set_gpu_busy(True)
                try:
                    response = await _llm_chat(True)
                except Exception as follow_err:
                    err_str = str(follow_err)
                    if "tool_use_failed" in err_str or "failed_generation" in err_str or "RateLimitError" in err_str:
                        logger.warning(f"Follow-up chat failed: {err_str}")
                        try:
                            response = await _llm_chat(False)
                        except Exception as final_err:
                            logger.error(f"Fallback chat also failed: {final_err}")
                            raise
                    else:
                        raise
                finally:
                    if _using_local_gpu and self.voice_manager:
                        self.voice_manager.set_gpu_busy(False)
            else:
                if response.tool_calls:
                    logger.warning(
                        "Stopped after {} tool rounds — asking model to wrap up without new tools",
                        _MAX_TOOL_ROUNDS,
                    )
                    await self.async_runtime.bus.publish(
                        RuntimeLogEvent(
                            "warning",
                            f"Tool limit ({_MAX_TOOL_ROUNDS}) reached; finishing in text-only mode.",
                        )
                    )
                    response = await _llm_chat(False)

            self.memory.add_message("user", user_text)
            self.memory.add_message("assistant", response.text)
            asyncio.create_task(self.memory.save_to_db())
            self.strategy_memory.record(
                category=category,
                provider=response.provider or preferred_provider or "unknown",
                tools_used=tool_names,
                latency_ms=int(response.usage.get("total_time_ms") or 0),
                prompt_tokens=int(response.usage.get("prompt_tokens", 0) or 0),
                completion_tokens=int(response.usage.get("completion_tokens", 0) or 0),
                success=True,
            )
            asyncio.create_task(self.strategy_memory.flush())

            await self.async_runtime.bus.publish(
                AIResponseEvent(
                    text=response.text,
                    tool_calls=[
                        {"name": tc.name, "args": tc.args, "id": tc.id}
                        for tc in (response.tool_calls or [])
                    ],
                    raw={"provider": response.provider, "usage": response.usage},
                )
            )

            if self.settings.get("voice_enabled", True):
                # publish() awaits on_tts_request fully (including audio playback),
                # so the mic is idle again before we return — no separate wait needed.
                await self.async_runtime.bus.publish(TTSRequestEvent(response.text))
            else:
                await self.async_runtime.bus.publish(StatusEvent("idle"))
        except Exception as exc:
            logger.error("Assistant request failed: {}", str(exc), exc_info=True)
            await self.async_runtime.bus.publish(
                RuntimeLogEvent("error", f"Assistant request failed: {exc}")
            )
            friendly = self._friendly_error(exc)
            await self.async_runtime.bus.publish(
                AIResponseEvent(
                    text=friendly,
                    raw={"error": str(exc)},
                )
            )
            await self.async_runtime.bus.publish(StatusEvent("error"))
        finally:
            if self.voice_manager:
                try:
                    await self.voice_manager.set_processing(False)
                except Exception:
                    pass
            # Safety net: one timer — cancel prior so rapid-fire commands do not stack sleeps.
            if self._idle_safety_task and not self._idle_safety_task.done():
                self._idle_safety_task.cancel()

            async def _ensure_idle():
                await asyncio.sleep(3.0)
                if self.ready:
                    try:
                        await self.async_runtime.bus.publish(StatusEvent("idle"))
                    except Exception:
                        pass

            try:
                self._idle_safety_task = asyncio.create_task(_ensure_idle())
            except RuntimeError:
                pass  # event loop shutting down — no harm

    async def _mirror_user_speech(self, event: UserSpeechEvent) -> None:
        self._emit_ui_event(
            {
                "type": "message",
                "sender": "YOU",
                "text": event.text,
                "origin": "voice",
            }
        )

    async def _mirror_ai_response(self, event: AIResponseEvent) -> None:
        self._emit_ui_event(
            {
                "type": "message",
                "sender": "JARVIS",
                "text": event.text,
                "origin": "assistant",
                "raw": event.raw,
            }
        )

    async def _mirror_partial_response(self, event: PartialResponseEvent) -> None:
        self._emit_ui_event(
            {
                "type": "partial_response",
                "delta": event.delta,
                "accumulated": event.accumulated,
            }
        )

    async def _mirror_proactive_help(self, event: ProactiveHelpEvent) -> None:
        self._emit_ui_event(
            {
                "type": "proactive_help",
                "suggestion": event.suggestion,
                "category": event.category,
            }
        )

    async def _mirror_transcription_chunk(self, event) -> None:
        self._emit_ui_event(
            {
                "type": "transcription_chunk",
                "text": event.text,
                "timestamp": event.timestamp,
                "session_id": event.session_id,
            }
        )

    async def _mirror_status(self, event: StatusEvent) -> None:
        self._emit_ui_event({"type": "status", "status": event.status})

    async def _mirror_mic(self, event: MicLevelEvent) -> None:
        self._emit_ui_event(
            {
                "type": "mic",
                "level": event.level,
                "speech_detected": event.speech_detected,
                "mode": event.mode,
            }
        )

    async def _mirror_log(self, event: RuntimeLogEvent) -> None:
        self._emit_ui_event(
            {
                "type": "log",
                "level": event.level,
                "message": event.message,
            }
        )

    async def _mirror_tool_call(self, event: ToolCallEvent) -> None:
        self._emit_ui_event(
            {
                "type": "tool_call",
                "name": event.name,
                "args": event.args,
            }
        )
        # Trigger computer-use overlay
        self._emit_ui_event({"type": "computer_use_start", "tool": event.name})

    async def _mirror_tool_result(self, event: ToolResultEvent) -> None:
        self._emit_ui_event(
            {
                "type": "tool_result",
                "name": event.name,
                "success": event.success,
                "result": event.result,
            }
        )
        # Dismiss computer-use overlay
        self._emit_ui_event({"type": "computer_use_end", "tool": event.name})

    def _emit_ui_event(self, payload: dict) -> None:
        self.bridge.event_received.emit(payload)

    @staticmethod
    def _categorize_request(text: str) -> str:
        lowered = text.lower()
        if any(token in lowered for token in ["browser", "site", "web", "url"]):
            return "browser.search"
        if any(token in lowered for token in ["screen", "window", "click", "desktop"]):
            return "screen.analyze"
        if any(token in lowered for token in ["code", "python", "script", "debug", "compile", "bug", "error", "cpp", "c++", "class"]):
            return "coding"
        if any(token in lowered for token in ["file", "folder", "directory"]):
            return "files.manage"
        if any(token in lowered for token in ["email", "mail"]):
            return "email.send"
        return "general.chat"

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        msg = str(exc).lower()
        if "api key" in msg or "authentication" in msg or "unauthorized" in msg or "401" in msg:
            return "No valid API key configured for the AI provider. Check your settings."
        if "rate limit" in msg or "429" in msg or "too many requests" in msg:
            return "The AI provider is rate-limiting requests. Try again in a moment."
        if "timeout" in msg or "timed out" in msg:
            return "The AI provider took too long to respond. Try again or switch providers."
        if "connection" in msg or "connect" in msg or "unreachable" in msg or "network" in msg:
            return "Can't reach the AI provider. Check your internet connection."
        if "all ai providers failed" in msg:
            return "None of the configured AI providers are responding. Check your API keys and internet connection in Settings."
        if "quota" in msg or "billing" in msg or "insufficient" in msg:
            return "Your API quota may be exhausted. Check your provider account billing."
        return f"Something went wrong: {exc}"

    @staticmethod
    def _should_capture_screen(text: str) -> bool:
        # Only capture when the user is asking about what's ON the screen,
        # not for simple app-launch / volume / time commands.
        # "open", "close", "navigate", "type", "scroll" alone don't need a
        # pre-capture — they trigger tool calls that auto-screenshot after acting.
        lowered = text.lower()
        keywords = [
            "screen", "what's on", "what is on", "screenshot",
            "desktop", "window", "click", "drag",
            "look", "see", "show me", "read", "describe",
        ]
        return any(keyword in lowered for keyword in keywords)

def main(demo_mode: bool = False):
    trace_dir = Path.home() / ".jarvis" / "logs"
    trace_dir.mkdir(parents=True, exist_ok=True)
    with (trace_dir / "startup_trace.log").open("a", encoding="utf-8") as handle:
        handle.write("app.main entered\n")

    setup_logging()
    logger.info("Launching JARVIS desktop application")
    qt_app = QApplication(sys.argv)
    from PyQt6.QtGui import QIcon as _QIcon
    _icon_path = Path(__file__).parent.parent / "jarvis.ico"
    if _icon_path.exists():
        qt_app.setWindowIcon(_QIcon(str(_icon_path)))
    from jarvis.utils.hotkey import GlobalHotkey

    # Handle Ctrl+C gracefully: signal the Qt event loop to quit instead of
    # throwing KeyboardInterrupt into the middle of a paintEvent.
    def _sigint_handler(signum, frame):
        logger.info("SIGINT received — shutting down cleanly")
        qt_app.quit()

    signal.signal(signal.SIGINT, _sigint_handler)

    # Qt's exec() blocks Python's signal handler.  Pulse a timer every 200 ms
    # so Python gets a chance to check for pending signals (including SIGINT).
    _sigint_timer = QTimer()
    _sigint_timer.setInterval(200)
    _sigint_timer.timeout.connect(lambda: None)
    _sigint_timer.start()

    # Show setup wizard on first launch (no config in %APPDATA%\JARVIS)
    from jarvis.utils.first_run import is_first_run
    if is_first_run() and not demo_mode:
        from jarvis.ui.setup_wizard import SetupWizard
        wizard = SetupWizard()
        result = wizard.exec()
        if result != SetupWizard.DialogCode.Accepted:
            logger.info("Setup wizard cancelled — exiting")
            sys.exit(0)

    global _runtime_instance
    runtime = JarvisRuntime()
    _runtime_instance = runtime
    window = AdvancedChatWindow(runtime, demo_mode=demo_mode)
    runtime.start()

    # Global hotkey Ctrl+Shift+J — restore window or start voice capture from any app
    def _hotkey_triggered():
        if window.isVisible() and not window.isMinimized():
            window.input_field.setFocus()
        else:
            window._restore_from_overlay()

    hotkey = GlobalHotkey("<ctrl>+<shift>+j", callback=_hotkey_triggered)
    hotkey.start()

    if "--minimized" in sys.argv:
        # Start as floating orb only — no main window.
        # set_background_state is async; fire and forget — it sets the voice mode.
        window.overlay_window.show_overlay()
        window.runtime.set_background_state(True)
    else:
        window.show()
        window.showNormal()
        window.raise_()
        window.activateWindow()
        from PyQt6.QtCore import QTimer as _QTimer
        _QTimer.singleShot(500, lambda: (window.showNormal(), window.raise_(), window.activateWindow()))

    exit_code = qt_app.exec()
    hotkey.stop()
    runtime.stop()
    sys.exit(exit_code)
