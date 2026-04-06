#!/usr/bin/env python3
from __future__ import annotations
"""
Clawmson Ollama chat integration.
Sends rolling conversation context (last 50 msgs) to Ollama, returns reply.
System prompt loaded from agents/configs/clawmson-chat.md.
"""

import os
import json
import requests
from pathlib import Path

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

_SYSTEM_PROMPT_PATH = Path.home() / "openclaw" / "agents" / "configs" / "clawmson-chat.md"
_SYSTEM_PROMPT_CACHE = None


def _load_system_prompt() -> str:
    global _SYSTEM_PROMPT_CACHE
    if _SYSTEM_PROMPT_CACHE is None:
        if _SYSTEM_PROMPT_PATH.exists():
            _SYSTEM_PROMPT_CACHE = _SYSTEM_PROMPT_PATH.read_text().strip()
        else:
            _SYSTEM_PROMPT_CACHE = "You are Clawmson, the AI assistant for OpenClaw."
    return _SYSTEM_PROMPT_CACHE


def reload_system_prompt():
    """Force re-read of system prompt on next call."""
    global _SYSTEM_PROMPT_CACHE
    _SYSTEM_PROMPT_CACHE = None


def chat(history: list, user_message: str, has_image: bool = False,
         model: str = None, memory_context: str = "") -> str:
    """
    Send conversation history + new user message to Ollama.
    history: list of {"role": "user"|"assistant", "content": str}
    memory_context: optional memory context to inject into system prompt
    Returns the assistant's reply as a string.
    Streams the response and assembles it before returning.
    """
    if model is None:
        import model_router as router
        # Pass has_image so router applies the vision override internally
        model = router.route(user_message, has_image=has_image)
    system_prompt = _load_system_prompt()
    if memory_context:
        system_prompt = f"{system_prompt}\n\n{memory_context}"

    messages = [{"role": "system", "content": system_prompt}]
    for entry in history:
        role = entry.get("role", "user")
        content = entry.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={"model": model, "messages": messages, "stream": True,
                  "options": {"num_ctx": int(os.environ.get("OPENCLAW_NUM_CTX", "16384"))}},
            stream=True,
            timeout=300
        )
        response.raise_for_status()

        parts = []
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            try:
                chunk = json.loads(raw_line)
                content = chunk.get("message", {}).get("content", "")
                if content:
                    parts.append(content)
                if chunk.get("done"):
                    break
            except json.JSONDecodeError:
                continue

        reply = "".join(parts).strip()
        return reply if reply else "(no response from model)"

    except requests.exceptions.ConnectionError:
        return "Ollama is not reachable. Start it with: ollama serve"
    except requests.exceptions.Timeout:
        return "Ollama timed out (>5 min). The model may be loading — try again."
    except requests.exceptions.HTTPError as e:
        return f"Ollama HTTP error: {e}"
    except Exception as e:
        return f"Chat error: {e}"
