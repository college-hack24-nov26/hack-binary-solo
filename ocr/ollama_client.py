"""Only talks to localhost Ollama. Never logs prompts, images or responses."""
import base64
import requests
from .config import Settings


class OllamaError(RuntimeError):
    pass


def health(s: Settings) -> dict:
    try:
        r = requests.get(f"{s.ollama_url}/api/tags", timeout=3)
        r.raise_for_status()
    except Exception:  # noqa: BLE001
        return {"ollamaUp": False, "modelPresent": False, "model": s.model}
    names = {m.get("name") for m in r.json().get("models", [])}
    return {"ollamaUp": True, "modelPresent": s.model in names, "model": s.model,
            "installed": sorted(n for n in names if n)}


def warm(s: Settings) -> None:
    """Load the model into memory and keep it there (no generation)."""
    try:
        requests.post(f"{s.ollama_url}/api/generate",
                      json={"model": s.model, "keep_alive": s.keep_alive}, timeout=s.timeout_s)
    except Exception:  # noqa: BLE001
        pass


def chat_json(s: Settings, system: str, user: str, image_jpeg: bytes, schema: dict) -> str:
    body = {
        "model": s.model,
        "stream": False,
        "think": False,
        "format": schema,
        "keep_alive": s.keep_alive,
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user, "images": [base64.b64encode(image_jpeg).decode()]},
        ],
    }
    try:
        r = requests.post(f"{s.ollama_url}/api/chat", json=body, timeout=s.timeout_s)
        r.raise_for_status()
        return r.json()["message"]["content"]
    except Exception as e:  # noqa: BLE001
        raise OllamaError(type(e).__name__) from None
