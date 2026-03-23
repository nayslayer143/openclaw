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
