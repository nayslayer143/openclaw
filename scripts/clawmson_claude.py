#!/usr/bin/env python3
from __future__ import annotations
"""
Clawmson Claude backend — replaces Ollama for Telegram conversations.
Uses Anthropic API with tool use for code execution.
Drop-in replacement: same chat() signature as clawmson_chat.py.
"""

import os
import json
import sqlite3
import subprocess
from pathlib import Path

# Load .env if not already in environment
_env_file = Path.home() / "openclaw" / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("CLAWMSON_CLAUDE_MODEL", "claude-sonnet-4-20250514")
MAX_TOKENS = 2048

_SYSTEM_PROMPT_PATH = Path.home() / "openclaw" / "agents" / "configs" / "clawmson-chat.md"
_SYSTEM_PROMPT_CACHE = None
_OPENCLAW_DIR = Path.home() / "openclaw"


def _load_system_prompt() -> str:
    global _SYSTEM_PROMPT_CACHE
    if _SYSTEM_PROMPT_CACHE is None:
        if _SYSTEM_PROMPT_PATH.exists():
            _SYSTEM_PROMPT_CACHE = _SYSTEM_PROMPT_PATH.read_text().strip()
        else:
            _SYSTEM_PROMPT_CACHE = "You are Clawmson, the AI assistant for OpenClaw."
        # Augment with Claude-specific capabilities
        _SYSTEM_PROMPT_CACHE += """

## Claude Backend Active
You are now powered by Claude (Anthropic API) instead of Ollama.
You have tool access: you can read files, edit code, run shell commands, and query databases.
When Jordan asks you to do something, DO IT — don't just describe what you'd do.
Keep responses concise for Telegram (under 500 words unless asked for detail).
You have full access to ~/openclaw/, ~/rivalclaw/, ~/quantumentalclaw/.
"""
    return _SYSTEM_PROMPT_CACHE


def reload_system_prompt():
    global _SYSTEM_PROMPT_CACHE
    _SYSTEM_PROMPT_CACHE = None


# Tools available to Claude via Telegram
TOOLS = [
    {
        "name": "run_command",
        "description": "Run a shell command on the local machine. Use for git, python, sqlite3, file operations, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to run"},
                "cwd": {"type": "string", "description": "Working directory (default: ~/openclaw)"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "read_file",
        "description": "Read a file from the filesystem. Returns the content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute file path"},
                "lines": {"type": "string", "description": "Line range like '1-50' (optional)"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "edit_file",
        "description": "Edit a file by replacing old_text with new_text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute file path"},
                "old_text": {"type": "string", "description": "Text to find and replace"},
                "new_text": {"type": "string", "description": "Replacement text"}
            },
            "required": ["path", "old_text", "new_text"]
        }
    },
    {
        "name": "query_db",
        "description": "Run a SQL query against a SQLite database. Use for checking trades, balances, bot stats.",
        "input_schema": {
            "type": "object",
            "properties": {
                "db_path": {"type": "string", "description": "Path to .db file (default: ~/.openclaw/clawmson.db)"},
                "query": {"type": "string", "description": "SQL query to execute"}
            },
            "required": ["query"]
        }
    },
]


def _execute_tool(name: str, input_data: dict) -> str:
    """Execute a tool call and return the result as a string."""
    try:
        if name == "run_command":
            cwd = input_data.get("cwd", str(_OPENCLAW_DIR))
            result = subprocess.run(
                input_data["command"], shell=True, capture_output=True, text=True,
                cwd=cwd, timeout=60
            )
            output = result.stdout + result.stderr
            return output[:3000] if output else "(no output)"

        elif name == "read_file":
            path = Path(input_data["path"]).expanduser()
            if not path.exists():
                return f"File not found: {path}"
            content = path.read_text()
            lines = input_data.get("lines")
            if lines:
                parts = lines.split("-")
                start = int(parts[0]) - 1
                end = int(parts[1]) if len(parts) > 1 else start + 1
                content = "\n".join(content.splitlines()[start:end])
            return content[:4000] if content else "(empty file)"

        elif name == "edit_file":
            path = Path(input_data["path"]).expanduser()
            if not path.exists():
                return f"File not found: {path}"
            content = path.read_text()
            if input_data["old_text"] not in content:
                return f"old_text not found in {path}"
            content = content.replace(input_data["old_text"], input_data["new_text"], 1)
            path.write_text(content)
            return f"Edited {path} successfully"

        elif name == "query_db":
            db_path = input_data.get("db_path", str(Path.home() / ".openclaw" / "clawmson.db"))
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(input_data["query"]).fetchall()
            conn.close()
            if not rows:
                return "(no results)"
            result = "\n".join(
                " | ".join(str(v) for v in dict(r).values())
                for r in rows[:50]
            )
            return result[:3000]

        return f"Unknown tool: {name}"
    except subprocess.TimeoutExpired:
        return "Command timed out (60s limit)"
    except Exception as e:
        return f"Tool error: {type(e).__name__}: {e}"


def chat(history: list, user_message: str, has_image: bool = False,
         model: str = None, memory_context: str = "") -> str:
    """
    Send conversation to Claude API with tool use.
    Same signature as clawmson_chat.chat() — drop-in replacement.
    """
    if not ANTHROPIC_API_KEY:
        # Fallback to Ollama if no API key
        import clawmson_chat as ollama
        return ollama.chat(history, user_message, has_image, model, memory_context)

    import requests

    system_prompt = _load_system_prompt()
    if memory_context:
        system_prompt = f"{system_prompt}\n\n{memory_context}"

    # Build messages in Anthropic format
    messages = []
    for entry in history[-20:]:  # Last 20 messages for context
        role = entry.get("role", "user")
        content = entry.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    # Tool use loop (max 5 rounds)
    for _ in range(5):
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model or MODEL,
                    "max_tokens": MAX_TOKENS,
                    "system": system_prompt,
                    "messages": messages,
                    "tools": TOOLS,
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.ConnectionError:
            return "Claude API is not reachable."
        except requests.exceptions.Timeout:
            return "Claude API timed out (>2 min)."
        except requests.exceptions.HTTPError as e:
            return f"Claude API error: {e}"
        except Exception as e:
            return f"Chat error: {e}"

        # Process response blocks
        text_parts = []
        tool_uses = []
        for block in data.get("content", []):
            if block["type"] == "text":
                text_parts.append(block["text"])
            elif block["type"] == "tool_use":
                tool_uses.append(block)

        # If no tool use, return the text response
        if not tool_uses or data.get("stop_reason") == "end_turn":
            reply = "\n".join(text_parts).strip()
            return reply if reply else "(no response)"

        # Execute tools and continue the loop
        # Add assistant message with tool use
        messages.append({"role": "assistant", "content": data["content"]})

        # Add tool results
        tool_results = []
        for tu in tool_uses:
            result = _execute_tool(tu["name"], tu["input"])
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": result,
            })
        messages.append({"role": "user", "content": tool_results})

    # If we exhausted the loop, return what we have
    return "\n".join(text_parts).strip() if text_parts else "(tool loop exhausted)"
