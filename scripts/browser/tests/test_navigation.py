import json
from pathlib import Path

def test_config_exists_and_has_required_keys():
    config_path = Path(__file__).parent.parent / "config.json"
    assert config_path.exists(), "config.json must exist"
    config = json.loads(config_path.read_text())
    for key in ("allowed_domains", "blocked_domains", "rate_limit_seconds",
                "default_timeout_ms", "stealth_mode", "proxy_url"):
        assert key in config, f"config.json missing key: {key}"
