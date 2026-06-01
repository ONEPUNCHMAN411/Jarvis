from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
from datetime import datetime

@dataclass
class WakeWordDetected:
    timestamp: float

@dataclass
class UserSpeechEvent:
    text: str
    confidence: float
    timestamp: float

@dataclass
class UserTextEvent:
    text: str
    source: str = "chat"

@dataclass
class AIResponseEvent:
    text: str
    tool_calls: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def response(self) -> str:
        return self.text

@dataclass
class PartialResponseEvent:
    delta: str
    accumulated: str = ""

@dataclass
class ToolCallEvent:
    name: str
    args: dict
    call_id: str

@dataclass
class ToolResultEvent:
    call_id: str
    name: str
    result: Any
    success: bool

@dataclass
class TTSRequestEvent:
    text: str
    priority: int = 0

@dataclass
class NotificationEvent:
    title: str
    body: str
    level: str = "info"

@dataclass
class StatusEvent:
    status: str

@dataclass
class MicLevelEvent:
    level: float
    speech_detected: bool = False
    mode: str = "idle"

@dataclass
class RuntimeLogEvent:
    level: str
    message: str

@dataclass
class ProactiveHelpEvent:
    suggestion: str
    category: str
    screenshot_path: str = ""

@dataclass
class TranscriptionChunkEvent:
    text: str
    timestamp: float
    session_id: str = ""

class Message(BaseModel):
    role: str
    content: str
    tool_call_id: str | None = None
    tool_calls: list[dict] | None = None  # raw tool_calls for assistant msgs (Groq API requirement)
    image_paths: list[str] = Field(default_factory=list)  # PNG file paths to embed as vision content
    timestamp: datetime = Field(default_factory=datetime.now)

class ToolCall(BaseModel):
    id: str
    name: str
    args: dict

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict = Field(default_factory=dict)

class AIResponse(BaseModel):
    text: str
    tool_calls: list[ToolCall] | None = None
    usage: dict = Field(default_factory=dict)
    provider: str = ""

class OllamaConfig(BaseModel):
    enabled: bool = True
    model: str = "llama3.1:8b"
    base_url: str = "http://localhost:11434"
    timeout: int = 30

class GroqConfig(BaseModel):
    enabled: bool = False
    api_key: str = ""
    model: str = "llama-3.1-70b-versatile"

class GeminiConfig(BaseModel):
    enabled: bool = False
    api_key: str = ""
    model: str = "gemini-2.0-flash"

class OpenRouterConfig(BaseModel):
    enabled: bool = False
    api_key: str = ""
    model: str = "meta-llama/llama-3.1-8b-instruct:free"

class AIConfig(BaseModel):
    primary_provider: str = "ollama"
    fallback_order: list[str] = Field(
        default_factory=lambda: ["ollama", "groq", "gemini", "openrouter"]
    )
    max_memory_messages: int = 50
    temperature: float = 0.7
    providers: dict[str, Any] = Field(default_factory=dict)

class VoiceConfig(BaseModel):
    enabled: bool = True
    wake_word: str = "hey jarvis"
    wake_word_sensitivity: float = 0.5
    always_listening: bool = False
    stt_model: str = "medium.en"
    stt_language: str = "en"
    tts_voice: str = "en-US-GuyNeural"
    tts_speed: str = "+0%"
    tts_engine: str = "edge-tts"
    input_device: str | None = None
    output_device: str | None = None

class ControlConfig(BaseModel):
    browser: str = "chromium"
    confirm_destructive: bool = True
    allowed_directories: list[str] = Field(
        default_factory=lambda: [str(Path.home())]
    )

class PluginConfig(BaseModel):
    email_enabled: bool = False
    telegram_enabled: bool = False
    spotify_enabled: bool = False
    image_gen_enabled: bool = True

class UIConfig(BaseModel):
    show_overlay: bool = True
    chat_hotkey: str = "ctrl+shift+j"
    theme: str = "dark"

class StartupConfig(BaseModel):
    auto_start: bool = True
    start_minimized: bool = True

class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "data/logs/jarvis.log"
    max_size: str = "10MB"
    retention: int = 7

class MCPConfig(BaseModel):
    servers: list[dict] = Field(default_factory=list)

class WatcherConfig(BaseModel):
    enabled: bool = False
    interval_seconds: int = 15
    provider: str = "auto"
    quiet_apps: list[str] = Field(default_factory=lambda: ["zoom", "teams", "discord", "netflix", "youtube"])
    max_suggestions_per_hour: int = 12

class JarvisConfig(BaseModel):
    name: str = "JARVIS"
    user_name: str = ""
    language: str = "en"
    data_dir: str = "data"
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    control: ControlConfig = Field(default_factory=ControlConfig)
    plugins: PluginConfig = Field(default_factory=PluginConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    startup: StartupConfig = Field(default_factory=StartupConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    watcher: WatcherConfig = Field(default_factory=WatcherConfig)
