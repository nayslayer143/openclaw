#!/usr/bin/env python3
"""
Browser security layer — credential vault, audit logging, domain scope, robots.txt.
Vault uses Fernet symmetric encryption keyed from machine-specific entropy.
"""
from __future__ import annotations

import json
import os
import re
import datetime
import hashlib
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional
from cryptography.fernet import Fernet


# ── Key derivation ────────────────────────────────────────────────────────────

def _derive_key() -> bytes:
    """
    Derive a stable Fernet key from machine-specific entropy.
    Uses hostname + username + a fixed salt — never leaves the machine.
    """
    import socket
    entropy = f"{socket.gethostname()}:{os.getlogin()}:openclaw-browser-vault-v1"
    raw = hashlib.sha256(entropy.encode()).digest()
    import base64
    return base64.urlsafe_b64encode(raw)


# ── Credential Vault ──────────────────────────────────────────────────────────

class CredentialVault:
    """
    Fernet-encrypted key/value store persisted to a local file.
    Keys and values are plain strings. Secrets never touch logs or CLI args.
    """

    def __init__(self, vault_path: Optional[Path] = None):
        if vault_path is None:
            vault_path = Path.home() / ".openclaw" / "browser-vault.enc"
        self._path = Path(vault_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fernet = Fernet(_derive_key())
        self._data: dict = self._load()

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            ciphertext = self._path.read_bytes()
            plaintext = self._fernet.decrypt(ciphertext)
            return json.loads(plaintext)
        except Exception:
            return {}

    def _save(self):
        plaintext = json.dumps(self._data).encode()
        ciphertext = self._fernet.encrypt(plaintext)
        self._path.write_bytes(ciphertext)

    def store(self, key: str, value: str):
        """Store a secret. Never log the value."""
        self._data[key] = value
        self._save()

    def retrieve(self, key: str) -> Optional[str]:
        """Retrieve a secret, or None if not found."""
        return self._data.get(key)

    def delete(self, key: str):
        self._data.pop(key, None)
        self._save()

    def keys(self) -> list:
        return list(self._data.keys())


# ── Audit Logger ──────────────────────────────────────────────────────────────

class AuditLogger:
    """
    Append-only JSONL audit log. One file per day in log_dir.
    Records every URL visited and every action taken.
    """

    def __init__(self, log_dir: Optional[Path] = None):
        if log_dir is None:
            log_dir = Path.home() / "openclaw" / "logs" / "browser"
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _log_path(self) -> Path:
        date = datetime.date.today().isoformat()
        return self._dir / f"browser-{date}.jsonl"

    def log(self, url: str, action: str, metadata: dict | None = None):
        entry = {
            "ts": datetime.datetime.now().isoformat(),
            "url": url,
            "action": action,
            **(metadata or {}),
        }
        with self._log_path().open("a") as f:
            f.write(json.dumps(entry) + "\n")


# ── Domain Scope ──────────────────────────────────────────────────────────────

class DomainScope:
    """
    Enforce domain allowlist/blocklist per task.
    If allowed is empty: all domains permitted except blocked.
    If allowed is non-empty: only those domains (minus blocked).
    """

    def __init__(self, allowed: list[str], blocked: list[str]):
        self._allowed = [d.lower().lstrip("*.") for d in allowed]
        self._blocked = [d.lower().lstrip("*.") for d in blocked]

    def _domain_of(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        return parsed.netloc.lower()

    def is_allowed(self, url: str) -> bool:
        domain = self._domain_of(url)
        # Check blocklist first
        for blocked in self._blocked:
            if domain == blocked or domain.endswith("." + blocked):
                return False
        # If allowlist is empty, allow everything not blocked
        if not self._allowed:
            return True
        # Must match allowlist
        for allowed in self._allowed:
            if domain == allowed or domain.endswith("." + allowed):
                return True
        return False


# ── robots.txt checker ────────────────────────────────────────────────────────

_robots_cache: dict[str, bool] = {}  # cache_key → allowed


def check_robots_txt(url: str, user_agent: str = "*") -> bool:
    """
    Returns True if the URL is allowed by robots.txt, False if disallowed.
    Caches per domain per process run. On fetch error, defaults to True (allow).
    """
    parsed = urllib.parse.urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    cache_key = f"{base}:{parsed.path}"

    if cache_key in _robots_cache:
        return _robots_cache[cache_key]

    try:
        robots_url = f"{base}/robots.txt"
        req = urllib.request.Request(robots_url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(req, timeout=5) as resp:
            robots_text = resp.read().decode("utf-8", errors="replace")
    except Exception:
        _robots_cache[cache_key] = True
        return True

    result = _parse_robots(robots_text, parsed.path, user_agent)
    _robots_cache[cache_key] = result
    return result


def _parse_robots(robots_text: str, path: str, user_agent: str) -> bool:
    """Returns True if path is allowed for user_agent."""
    lines = robots_text.splitlines()
    in_relevant_section = False
    disallow_rules: list[str] = []
    allow_rules: list[str] = []

    for line in lines:
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        if line.lower().startswith("user-agent:"):
            ua = line[len("user-agent:"):].strip()
            in_relevant_section = (ua == "*" or ua.lower() == user_agent.lower())
            continue
        if in_relevant_section:
            if line.lower().startswith("disallow:"):
                rule = line[len("disallow:"):].strip()
                if rule:
                    disallow_rules.append(rule)
            elif line.lower().startswith("allow:"):
                rule = line[len("allow:"):].strip()
                if rule:
                    allow_rules.append(rule)

    for rule in allow_rules:
        if path.startswith(rule):
            return True
    for rule in disallow_rules:
        if path.startswith(rule):
            return False
    return True


# ── Module-level singleton helpers ────────────────────────────────────────────

_default_vault: Optional[CredentialVault] = None
_default_audit: Optional[AuditLogger] = None


def get_vault() -> CredentialVault:
    global _default_vault
    if _default_vault is None:
        _default_vault = CredentialVault()
    return _default_vault


def get_audit_logger() -> AuditLogger:
    global _default_audit
    if _default_audit is None:
        _default_audit = AuditLogger()
    return _default_audit
