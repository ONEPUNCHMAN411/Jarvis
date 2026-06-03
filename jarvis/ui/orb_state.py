def classify_response_style(text: str) -> str:
    lowered = text.lower()

    if "!" in text or any(token in lowered for token in ["immediately", "alert", "warning", "critical"]):
        return "emphatic"

    analytical_tokens = [
        "because",
        "cause",
        "ranked",
        "likely",
        "analysis",
        "diagnostic",
        "steps",
        "three",
    ]
    if any(token in lowered for token in analytical_tokens):
        return "analytical"

    return "calm"
