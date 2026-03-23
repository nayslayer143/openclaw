#!/usr/bin/env python3
"""
3-agent inline Ollama debate for REVIEW-range skills.
Runs: defender → attacker → judge.
All calls use qwen3:30b with 120s timeout. Fallback: qwen3:32b.
"""
from __future__ import annotations
import json
import re
import requests

OLLAMA_BASE    = "http://localhost:11434"
PRIMARY_MODEL  = "qwen3:30b"
FALLBACK_MODEL = "qwen3:32b"
TIMEOUT_S      = 120


def _call_ollama(prompt: str, model: str = PRIMARY_MODEL) -> str:
    """Single non-streaming Ollama call. Returns content string."""
    try:
        r = requests.post(
            f"{OLLAMA_BASE}/api/chat",
            json={
                "model":    model,
                "messages": [{"role": "user", "content": prompt}],
                "stream":   False,
            },
            timeout=TIMEOUT_S,
        )
        r.raise_for_status()
        return r.json()["message"]["content"]
    except requests.exceptions.Timeout:
        raise
    except Exception:
        # Try fallback model once
        try:
            r = requests.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model":    FALLBACK_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream":   False,
                },
                timeout=TIMEOUT_S,
            )
            r.raise_for_status()
            return r.json()["message"]["content"]
        except Exception:
            raise


def _parse_judge(response: str) -> dict | None:
    """
    Extract JSON from judge response. Returns dict or None on failure.
    Tries full parse first, then regex extraction.
    """
    # Try direct parse
    try:
        return json.loads(response.strip())
    except json.JSONDecodeError:
        pass

    # Regex fallback: find first {...} block containing "verdict"
    m = re.search(r'\{[^{}]*"verdict"[^{}]*\}', response, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def run_debate(code: str, findings: list, original_score: int) -> dict:
    """
    Run the 3-agent debate.
    Returns:
      adjusted_score : int
      verdict        : str (APPROVE | BLOCK | None if parse_failed)
      reasoning      : str
      transcript     : dict with defender/attacker/judge keys
      parse_failed   : bool
    """
    findings_text = "\n".join(
        f"  - [{f.severity}] {f.category} line {f.line_no}: {f.snippet}"
        for f in findings
    ) or "  (no findings)"

    # ── Agent A: Defender ─────────────────────────────────────────────────────
    defender_prompt = (
        f"You are a security reviewer arguing this skill code is SAFE.\n"
        f"Code:\n```\n{code[:3000]}\n```\n"
        f"Scanner findings:\n{findings_text}\n\n"
        f"Argue that this skill is safe. Explain its legitimate functionality. "
        f"Address each finding specifically. Be concise (max 300 words)."
    )
    try:
        defender = _call_ollama(defender_prompt)
    except Exception as e:
        return _failed_result(original_score, str(e))

    # ── Agent B: Attacker ─────────────────────────────────────────────────────
    attacker_prompt = (
        f"You are a security auditor hunting for exploits.\n"
        f"Code:\n```\n{code[:3000]}\n```\n"
        f"Scanner findings:\n{findings_text}\n\n"
        f"Defender's argument:\n{defender[:500]}\n\n"
        f"Find exploits, injection vectors, data leaks. "
        f"Challenge every claim from the defender. Be concise (max 300 words)."
    )
    try:
        attacker = _call_ollama(attacker_prompt)
    except Exception as e:
        return _failed_result(original_score, str(e))

    # ── Agent C: Judge ────────────────────────────────────────────────────────
    judge_prompt = (
        f"You are the final security arbiter.\n"
        f"Code:\n```\n{code[:3000]}\n```\n"
        f"Scanner findings:\n{findings_text}\n"
        f"Defender:\n{defender[:500]}\n"
        f"Attacker:\n{attacker[:500]}\n\n"
        f"Produce your final verdict as valid JSON only, no other text:\n"
        f'{{"verdict": "APPROVE" or "BLOCK", "adjusted_score": 0-100, "reasoning": "..."}}'
    )
    try:
        judge = _call_ollama(judge_prompt)
    except Exception as e:
        return _failed_result(original_score, str(e))

    parsed = _parse_judge(judge)
    if not parsed or "adjusted_score" not in parsed:
        return {
            "adjusted_score": original_score,
            "verdict":        None,
            "reasoning":      "Judge parse failed",
            "transcript":     {"defender": defender, "attacker": attacker, "judge": judge},
            "parse_failed":   True,
        }

    adj_score = max(0, min(100, int(parsed.get("adjusted_score", original_score))))
    return {
        "adjusted_score": adj_score,
        "verdict":        parsed.get("verdict"),
        "reasoning":      parsed.get("reasoning", ""),
        "transcript":     {"defender": defender, "attacker": attacker, "judge": judge},
        "parse_failed":   False,
    }


def _failed_result(original_score: int, reason: str) -> dict:
    return {
        "adjusted_score": original_score,
        "verdict":        None,
        "reasoning":      f"Debate failed: {reason}",
        "transcript":     {},
        "parse_failed":   True,
    }
