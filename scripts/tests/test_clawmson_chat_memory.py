#!/usr/bin/env python3
"""Test that chat() injects memory_context into the system prompt."""
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

_SCRIPTS = Path(__file__).parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import unittest


class TestChatMemoryContext(unittest.TestCase):
    def _mock_response(self, content: str):
        """Build a mock streaming response."""
        chunk = json.dumps({"message": {"content": content}, "done": True})
        mock_resp = MagicMock()
        mock_resp.iter_lines.return_value = [chunk.encode()]
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_memory_context_injected(self):
        """memory_context is appended to system prompt when provided."""
        captured = []

        def fake_post(url, json=None, **kwargs):
            captured.append(json)
            return self._mock_response("reply")

        with patch("clawmson_chat.requests.post", side_effect=fake_post):
            import clawmson_chat
            clawmson_chat.chat([], "hello", memory_context="### Memory Context\nJordan prefers X")

        self.assertEqual(len(captured), 1)
        system_msg = captured[0]["messages"][0]
        self.assertEqual(system_msg["role"], "system")
        self.assertIn("### Memory Context", system_msg["content"])
        self.assertIn("Jordan prefers X", system_msg["content"])

    def test_no_memory_context_unchanged(self):
        """Without memory_context, system prompt is unchanged."""
        captured = []

        def fake_post(url, json=None, **kwargs):
            captured.append(json)
            return self._mock_response("reply")

        with patch("clawmson_chat.requests.post", side_effect=fake_post):
            import clawmson_chat
            clawmson_chat.chat([], "hello")

        system_content = captured[0]["messages"][0]["content"]
        self.assertNotIn("### Memory Context", system_content)


if __name__ == "__main__":
    unittest.main()
