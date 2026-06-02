from copy import deepcopy

from jarvis.ui.provider_help import PROVIDER_HELP
from jarvis.voice.voice_profiles import get_voice_profile

def get_provider_help(provider_name: str) -> dict:
    return deepcopy(
        PROVIDER_HELP.get(
            provider_name,
            {
                "label": provider_name.title(),
                "url": "",
                "instructions": "No setup instructions available.",
            },
        )
    )

def apply_settings_to_config(config, settings: dict):
    updated = config.model_copy(deep=True)
    provider_updates = settings.get("providers", {})

    # Fields that must never be overwritten with an empty/blank value from the UI.
    # If the YAML config has a real value and the UI sends an empty string (user
    # opened Settings but never typed a path), we keep the YAML value.
    _PRESERVE_IF_NONEMPTY = {"model_path", "mmproj_path", "draft_model_path", "api_key", "base_url"}

    for provider_name, provider_settings in provider_updates.items():
        merged = dict(updated.ai.providers.get(provider_name, {}))
        for k, v in provider_settings.items():
            # Don't clobber a meaningful config value with an empty UI string
            if k in _PRESERVE_IF_NONEMPTY and isinstance(v, str) and not v.strip():
                if merged.get(k):  # YAML had a real value — keep it
                    continue
            merged[k] = v
        updated.ai.providers[provider_name] = merged

    if "voice_enabled" in settings:
        updated.voice.enabled = bool(settings["voice_enabled"])
    if "background_mode" in settings:
        updated.voice.always_listening = settings["background_mode"] == "always_listening"
    if "voice_profile" in settings:
        profile = get_voice_profile(settings["voice_profile"])
        updated.voice.tts_voice = profile["voice"]
        updated.voice.tts_speed = profile["rate"]
    if "wake_word_sensitivity" in settings:
        updated.voice.wake_word_sensitivity = float(settings["wake_word_sensitivity"])
    if "stt_model" in settings:
        updated.voice.stt_model = str(settings["stt_model"])
    if "stt_language" in settings:
        updated.voice.stt_language = str(settings["stt_language"])
    if "input_device" in settings:
        updated.voice.input_device = settings["input_device"] or None

    return updated
