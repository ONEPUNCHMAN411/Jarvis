import re

def is_meaningful_transcript(text: str, min_alnum: int = 2) -> bool:
    """
    Ignore STT noise like ".", "...", or single-letter hallucinations so we do not
    send empty-looking phantom requests to the LLM.
    """
    t = text.strip()
    if not t:
        return False
    alnum = sum(1 for c in t if c.isalnum())
    return alnum >= min_alnum

def extract_command_from_transcript(
    transcript: str,
    wake_phrase: str,
    require_wake_phrase: bool,
) -> str:
    cleaned = " ".join(transcript.strip().split())
    if not cleaned:
        return ""

    lowered = cleaned.lower()
    wake = wake_phrase.strip().lower()

    if not require_wake_phrase:
        return cleaned

    tokens = _normalize_tokens(cleaned)
    wake_tokens = _normalize_tokens(wake)
    if not tokens or not wake_tokens:
        return ""

    primary_name = wake_tokens[-1]
    aliases = [
        wake_tokens,
        ["hey", wake_tokens[-1]],
    ]

    for alias in aliases:
        index = _find_subsequence(tokens, alias)
        if index == -1:
            continue
        command_tokens = tokens[index + len(alias):]
        # Only return if we actually have a command or it's a clear wake-only intent
        return " ".join(command_tokens).strip()

    return ""

def _normalize_tokens(text: str) -> list[str]:
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return [token for token in normalized.split() if token]

def _find_subsequence(tokens: list[str], needle: list[str]) -> int:
    limit = len(tokens) - len(needle) + 1
    for index in range(max(limit, 0)):
        if tokens[index:index + len(needle)] == needle:
            return index
    return -1
