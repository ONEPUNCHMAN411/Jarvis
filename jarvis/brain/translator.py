
import threading

from loguru import logger

_AVAILABLE = False
try:
    from deep_translator import GoogleTranslator
    _AVAILABLE = True
except ImportError:
    pass

_LANGUAGES = {
    "af": "afrikaans", "sq": "albanian", "am": "amharic", "ar": "arabic",
    "az": "azerbaijani", "eu": "basque", "be": "belarusian", "bn": "bengali",
    "bs": "bosnian", "bg": "bulgarian", "ca": "catalan",
    "zh-cn": "chinese simplified", "zh-tw": "chinese traditional",
    "hr": "croatian", "cs": "czech", "da": "danish", "nl": "dutch",
    "en": "english", "eo": "esperanto", "et": "estonian", "fi": "finnish",
    "fr": "french", "gl": "galician", "ka": "georgian", "de": "german",
    "el": "greek", "gu": "gujarati", "ht": "haitian creole", "ha": "hausa",
    "he": "hebrew", "hi": "hindi", "hu": "hungarian", "is": "icelandic",
    "ig": "igbo", "id": "indonesian", "ga": "irish", "it": "italian",
    "ja": "japanese", "jv": "javanese", "kn": "kannada", "kk": "kazakh",
    "km": "khmer", "ko": "korean", "lo": "lao", "la": "latin",
    "lv": "latvian", "lt": "lithuanian", "mk": "macedonian", "ms": "malay",
    "ml": "malayalam", "mt": "maltese", "mi": "maori", "mr": "marathi",
    "mn": "mongolian", "my": "myanmar", "ne": "nepali", "no": "norwegian",
    "fa": "persian", "pl": "polish", "pt": "portuguese", "pa": "punjabi",
    "ro": "romanian", "ru": "russian", "sr": "serbian", "si": "sinhala",
    "sk": "slovak", "sl": "slovenian", "so": "somali", "es": "spanish",
    "sw": "swahili", "sv": "swedish", "tl": "filipino", "ta": "tamil",
    "te": "telugu", "th": "thai", "tr": "turkish", "uk": "ukrainian",
    "ur": "urdu", "uz": "uzbek", "vi": "vietnamese", "cy": "welsh",
    "xh": "xhosa", "yi": "yiddish", "yo": "yoruba", "zu": "zulu",
}


class Translator:
    """Wraps deep-translator for text translation between any two languages."""

    def translate(self, text: str, target: str = "en", source: str = "auto") -> str:
        if not _AVAILABLE:
            raise RuntimeError(
                "deep-translator not installed. Run: pip install deep-translator"
            )
        if not text.strip():
            return ""
        try:
            t = GoogleTranslator(source=source, target=target)
            result = t.translate(text)
            return result or text
        except Exception as e:
            logger.error(f"Translation failed: {e}")
            raise

    def detect_language(self, text: str) -> str:
        if not _AVAILABLE:
            raise RuntimeError("deep-translator not installed")
        if not text.strip():
            return "unknown"
        try:
            from deep_translator import single_detection
            lang = single_detection(text, api_key="")
            return lang or "unknown"
        except Exception as e:
            logger.warning(f"Language detection failed: {e}")
            return "unknown"

    def list_languages(self) -> dict[str, str]:
        return dict(_LANGUAGES)


_instance: Translator | None = None
_lock = threading.Lock()


def get_translator() -> Translator:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = Translator()
    return _instance
