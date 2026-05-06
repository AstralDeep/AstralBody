"""Feature 013 follow-up — sanitizer for leaked tool-call tokens.

Some open-weight LLMs (Llama, Qwen, etc.) emit their tool-call
tokenization as plain text even when instructed not to. The user-visible
symptom is a chat bubble that reads
``<|tool_call>call:...{...}<tool_call|>``. The orchestrator strips these
patterns post-hoc via ``_sanitize_text_response``.
"""
from __future__ import annotations

import os
import sys
import unittest

_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from orchestrator.orchestrator import _sanitize_text_response  # noqa: E402


class TestSanitizeTextResponse(unittest.TestCase):
    def test_passes_clean_text_through_unchanged(self) -> None:
        text = "Hello! I can help with that."
        self.assertEqual(_sanitize_text_response(text), text)

    def test_strips_llama_style_tool_call_pair(self) -> None:
        # The exact pattern reported by the user.
        bad = "<|tool_call>call:weather-1:get_current_weather{lat: 38.0345, lon: -84.5089}<tool_call|>"
        out = _sanitize_text_response(bad)
        # All-leaked content collapses to the friendly fallback.
        self.assertNotIn("tool_call", out)
        self.assertNotIn("get_current_weather", out)
        self.assertIn("agents", out.lower())

    def test_strips_xml_style_tool_call(self) -> None:
        bad = 'Sure: <tool_call>{"name": "search_web", "args": {}}</tool_call>'
        out = _sanitize_text_response(bad)
        self.assertEqual(out, "Sure:")

    def test_strips_function_call_form(self) -> None:
        bad = "<function_call>get_weather(lat=1, lon=2)</function_call> done"
        out = _sanitize_text_response(bad)
        self.assertEqual(out, "done")

    def test_strips_llama3_section_markers(self) -> None:
        bad = (
            "Here's the result:\n"
            "<|tool_calls_section_begin|>\n"
            '{"name": "x", "arguments": {}}\n'
            "<|tool_calls_section_end|>"
        )
        out = _sanitize_text_response(bad)
        self.assertNotIn("tool_calls_section", out)
        self.assertEqual(out, "Here's the result:")

    def test_strips_bracket_tool_calls(self) -> None:
        bad = "Result: [TOOL_CALLS]get_weather(){}[/TOOL_CALLS]"
        out = _sanitize_text_response(bad)
        self.assertEqual(out, "Result:")

    def test_falls_back_to_friendly_message_when_only_tokens(self) -> None:
        # When stripping leaves nothing, the user gets an actionable hint
        # pointing at the picker — not an empty bubble.
        out = _sanitize_text_response("<|tool_call|>x<|tool_call|>")
        self.assertIn("Tools & Agents", out)
        self.assertIn("agents", out.lower())

    def test_strips_dangling_open_token_without_close(self) -> None:
        bad = "Working: <|tool_call|> something happened"
        out = _sanitize_text_response(bad)
        self.assertNotIn("|tool_call|", out)

    def test_handles_empty_input(self) -> None:
        self.assertEqual(_sanitize_text_response(""), "")
        self.assertEqual(_sanitize_text_response(None), None)  # type: ignore[arg-type]

    def test_preserves_legitimate_mention_of_tool_call(self) -> None:
        # The patterns are anchored on the bracket / pipe markers, so a
        # plain English mention of "tool call" survives.
        text = "I would normally make a tool call here, but no agents are enabled."
        self.assertEqual(_sanitize_text_response(text), text)


if __name__ == "__main__":
    unittest.main()
