# scripts/clawteam/tests/test_chub.py
"""Tests for chub.py — FORGE context injection."""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_detect_backtick():
    """Backtick-wrapped name is extracted as a candidate."""
    from clawteam.chub import _extract_candidates
    result = _extract_candidates("use `requests` to fetch data from an API")
    assert "requests" in result


def test_detect_import():
    """import statement extracts the module name."""
    from clawteam.chub import _extract_candidates
    result = _extract_candidates("import boto3\nupload the file to S3")
    assert "boto3" in result


def test_short_candidate_filtered():
    """Candidates shorter than 4 chars are dropped before subprocess."""
    from clawteam.chub import _extract_candidates
    # 'os' and 're' are 2 chars — must be filtered out
    result = _extract_candidates("import os\nuse re to match")
    assert "os" not in result
    assert "re" not in result


def test_candidate_with_spaces_filtered():
    """Backtick-wrapped multi-word name is rejected by shape filter."""
    from clawteam.chub import _extract_candidates
    # backtick pattern captures "some library" (contains a space)
    result = _extract_candidates("use `some library` to process data")
    # "some library" contains a space — shape filter `re.match(r'^[\w][\w.\-]*$', c)` drops it
    assert "some library" not in result


def test_cap_at_three():
    """Prompts with more than 3 candidates return at most 3."""
    from clawteam.chub import _extract_candidates
    result = _extract_candidates("`numpy` `pandas` `scipy` `sklearn` `matplotlib`")
    assert len(result) == 3


def _make_proc(stdout: bytes = b"", returncode: int = 0):
    """Build a mock CompletedProcess."""
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m


def test_lookup_success():
    """Successful chub search+get returns formatted doc string."""
    import json as _json
    from clawteam.chub import fetch_chub_context
    search_out = _json.dumps([{"id": "requests", "name": "requests"}]).encode()
    doc_body = "Sample requests docs."
    search_proc = _make_proc(stdout=search_out)
    get_proc = _make_proc(stdout=doc_body.encode())
    with patch("clawteam.chub.subprocess.run", side_effect=[search_proc, get_proc]):
        result = fetch_chub_context("use `requests` to call an endpoint")
    assert result.startswith("[API DOCS: requests]\n")
    assert doc_body in result


def test_cap_boundary():
    """Doc body is sliced to exactly 3000 chars, not 3001."""
    import json as _json
    from clawteam.chub import fetch_chub_context
    search_out = _json.dumps([{"id": "requests", "name": "requests"}]).encode()
    doc_body = "X" * 3001
    search_proc = _make_proc(stdout=search_out)
    get_proc = _make_proc(stdout=doc_body.encode())
    with patch("clawteam.chub.subprocess.run", side_effect=[search_proc, get_proc]):
        result = fetch_chub_context("use `requests` to call an endpoint")
    label = "[API DOCS: requests]\n"
    body = result[len(label):]
    assert len(body) == 3000
    assert body == "X" * 3000


def test_graceful_chub_not_found():
    """FileNotFoundError (chub not on PATH) → returns empty string."""
    from clawteam.chub import fetch_chub_context
    with patch("clawteam.chub.subprocess.run", side_effect=FileNotFoundError):
        result = fetch_chub_context("use `requests` to fetch data")
    assert result == ""


def test_graceful_no_match():
    """Empty search results → returns empty string."""
    import json as _json
    from clawteam.chub import fetch_chub_context
    search_proc = _make_proc(stdout=_json.dumps([]).encode())
    with patch("clawteam.chub.subprocess.run", return_value=search_proc):
        result = fetch_chub_context("use `requests` to fetch data")
    assert result == ""


def test_graceful_non_list_json():
    """chub search returns valid JSON that is not a list → returns empty string."""
    import json as _json
    from clawteam.chub import fetch_chub_context
    search_proc = _make_proc(stdout=_json.dumps({"error": "rate limited"}).encode())
    with patch("clawteam.chub.subprocess.run", return_value=search_proc):
        result = fetch_chub_context("use `requests` to fetch data")
    assert result == ""


def test_graceful_timeout():
    """subprocess.TimeoutExpired → returns empty string."""
    import subprocess as _sp
    from clawteam.chub import fetch_chub_context
    with patch("clawteam.chub.subprocess.run", side_effect=_sp.TimeoutExpired("chub", 3)):
        result = fetch_chub_context("use `requests` to fetch data")
    assert result == ""


def test_graceful_name_mismatch():
    """chub search top result name does not match candidate → returns empty string."""
    import json as _json
    from clawteam.chub import fetch_chub_context
    # search for "boto3" but chub returns "django" as top result
    search_proc = _make_proc(
        stdout=_json.dumps([{"id": "django", "name": "django"}]).encode()
    )
    with patch("clawteam.chub.subprocess.run", return_value=search_proc):
        result = fetch_chub_context("use `boto3` to upload files")
    assert result == ""


def test_graceful_nonzero_exit_search():
    """Non-zero returncode from chub search → returns empty string."""
    from clawteam.chub import fetch_chub_context
    search_proc = _make_proc(stdout=b"", returncode=1)
    with patch("clawteam.chub.subprocess.run", return_value=search_proc):
        result = fetch_chub_context("use `requests` to fetch data")
    assert result == ""
