from copy import deepcopy

# NOTE: edge-tts pitch MUST be integer Hz (e.g. +0Hz, -5Hz, +10Hz).
# Decimal values like -0.5Hz cause a hard error and silence voice output.
#
# Voice profiles are modelled after AI characters from film/pop culture or
# distinct personality archetypes that suit a personal desktop assistant.
# All voices are Microsoft Neural voices available through edge-tts.
#
# JARVIS (Paul Bettany, Iron Man 1-3 / Avengers):
#   - Received Pronunciation (RP) British English
#   - Mid-to-low pitch, measured cadence, unhurried but never slow
#   - Dry wit, formal register, precision over expressiveness
#   - en-GB-RyanNeural is the closest available: clean RP accent, neutral-
#     authoritative timbre. A slight speed-up (+10 %) matches Bettany's
#     crisp delivery; a modest pitch dip (-5 Hz) adds gravitas without
#     sounding artificially deep.
#
# FRIDAY (Irish, Iron Man 3 / Avengers):
#   - Irish accent, warmer and lighter than JARVIS
#   - en-IE-ConnorNeural (male) or en-IE-EmilyNeural (female); Emily is
#     closer to the movie portrayal by Kerry Condon — warm, conversational.
#   - Slight speed-up to keep the natural lilt from dragging.
#
# ATLAS — original deep-American-male archetype:
#   - en-US-BrianNeural has a naturally low, broadcast-quality resonance.
#   - Slowed slightly (-5 %) for the deliberate, analytical feel of a
#     mission-control voice.  Pitch pushed down (-8 Hz) for authority.
#
# NOVA — warm American female, approachable:
#   - en-US-JennyNeural is Microsoft's flagship conversational US-female;
#     articulate, natural, friendly without being saccharine.
#   - Stock speed; tiny pitch lift (+2 Hz) for brightness.
#
# SAGE — British female, precise and composed:
#   - en-GB-SoniaNeural: clear RP accent, measured, professional.
#   - No speed change needed; -3 Hz pitch keeps it authoritative.
#
# ARIA — neutral, clear, speed-optimised for rapid responses:
#   - en-US-AnaNeural: clear, gender-neutral-leaning US voice with minimal
#     accent colouring.  Speed boosted (+18 %) so short responses feel
#     snappy on fast hardware.
_VOICE_PROFILES = [
    {
        "id": "jarvis",
        "label": "JARVIS — British RP, calm & authoritative",
        "description": (
            "Closest match to Paul Bettany's JARVIS: Received Pronunciation British, "
            "measured pace, dry precision.  Best for formal or technical interactions."
        ),
        "voice": "en-GB-RyanNeural",
        "rate": "+10%",
        "pitch": "-5Hz",
    },
    {
        "id": "friday",
        "label": "FRIDAY — Irish, warm & conversational",
        "description": (
            "Inspired by JARVIS's successor in the MCU: Irish accent, lighter register, "
            "naturally conversational.  Great for everyday assistant tasks."
        ),
        "voice": "en-IE-EmilyNeural",
        "rate": "+8%",
        "pitch": "+0Hz",
    },
    {
        "id": "atlas",
        "label": "Atlas — deep American male, analytical",
        "description": (
            "Deep broadcast-quality American voice.  Calm, deliberate cadence suits "
            "mission-critical or system-status announcements."
        ),
        "voice": "en-US-BrianNeural",
        "rate": "-5%",
        "pitch": "-8Hz",
    },
    {
        "id": "nova",
        "label": "Nova — warm American female, friendly",
        "description": (
            "Microsoft's flagship conversational US female voice.  Natural, articulate, "
            "and approachable — ideal for general day-to-day use."
        ),
        "voice": "en-US-JennyNeural",
        "rate": "+0%",
        "pitch": "+2Hz",
    },
    {
        "id": "sage",
        "label": "Sage — British female, precise & composed",
        "description": (
            "Clear Received Pronunciation British female voice.  Professional and composed; "
            "works well for reading documents, summaries, or formal reports."
        ),
        "voice": "en-GB-SoniaNeural",
        "rate": "+0%",
        "pitch": "-3Hz",
    },
    {
        "id": "aria",
        "label": "Aria — neutral US, fast & clear",
        "description": (
            "Speed-optimised neutral American voice.  Minimal accent colouring and high "
            "clarity make it ideal for quick one-liners and rapid response modes."
        ),
        "voice": "en-US-AnaNeural",
        "rate": "+18%",
        "pitch": "+0Hz",
    },
]

_DEFAULT_CUSTOM_PROFILE = {
    "id": "custom",
    "label": "Custom imported profile",
    "description": "User-configured custom voice profile.",
    "voice": "en-US-EricNeural",
    "rate": "-2%",
    "pitch": "+0Hz",
}


def builtin_voice_profiles(custom_profile: dict | None = None) -> list[dict]:
    profiles = [deepcopy(profile) for profile in _VOICE_PROFILES]
    profiles.append(normalize_custom_profile(custom_profile))
    return profiles


def get_voice_profile(profile_id: str, custom_profile: dict | None = None) -> dict:
    if profile_id == "custom":
        return normalize_custom_profile(custom_profile)

    for profile in _VOICE_PROFILES:
        if profile["id"] == profile_id:
            return deepcopy(profile)
    return deepcopy(_VOICE_PROFILES[0])


def normalize_custom_profile(profile: dict | None) -> dict:
    merged = deepcopy(_DEFAULT_CUSTOM_PROFILE)
    if profile:
        merged.update({key: value for key, value in profile.items() if value not in (None, "")})
    merged["id"] = "custom"
    return merged
