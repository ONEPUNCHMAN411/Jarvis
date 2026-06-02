"""OpenAI-compatible serialization of conversation messages (tool rounds included)."""


from jarvis.brain.image_utils import load_image_data_url
from jarvis.models import Message

def messages_to_openai(messages: list[Message], system_prompt: str | None = None) -> list[dict]:
    """
    Build the chat payload expected by Mistral / Groq / OpenAI-compatible APIs.
    Tool-result turns must include role \"tool\" and \"tool_call_id\"; assistant
    turns that invoked tools must include \"tool_calls\".
    User messages with image_paths are converted to multipart content (vision).
    """
    formatted: list[dict] = []
    if system_prompt:
        formatted.append({"role": "system", "content": system_prompt})

    for msg in messages:
        if msg.role == "user" and msg.image_paths:
            parts: list[dict] = []
            for path in msg.image_paths:
                data_url = load_image_data_url(path)
                if data_url:
                    parts.append({"type": "image_url", "image_url": {"url": data_url}})
            if msg.content:
                parts.append({"type": "text", "text": msg.content})
            entry: dict = {"role": "user", "content": parts}
        else:
            entry = {
                "role": msg.role,
                "content": msg.content if msg.content is not None else "",
            }

        if msg.tool_call_id:
            entry["tool_call_id"] = msg.tool_call_id
        if msg.tool_calls:
            entry["tool_calls"] = msg.tool_calls
        formatted.append(entry)

    return formatted
