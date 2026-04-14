"""Tests for the LLM session generation pipeline.

Mocks the LLM call (ask_llm) and Firestore to verify:
- The prompt includes the description and overrides
- The generated conversation is written via the ingest pipeline
- Dry-run mode skips writing
"""

from unittest.mock import MagicMock, patch

import pytest

from seerai.generate import (
    GeneratedConversation,
    GeneratedEvent,
    generate_session,
)


def _fake_conversation(**overrides) -> GeneratedConversation:
    defaults = dict(
        provider="anthropic",
        platform="vscode",
        utility="useful",
        events=[
            GeneratedEvent(
                event_type="user_message",
                content="How do I fix CORS?",
            ),
            GeneratedEvent(
                event_type="ai_message",
                content="Add the Access-Control-Allow-Origin header.",
                metadata={"model": "claude-sonnet-4", "tokens": 120, "latency_ms": 450},
            ),
        ],
    )
    defaults.update(overrides)
    return GeneratedConversation(**defaults)


class TestGeneratedConversation:
    def test_minimum_two_events(self):
        """Conversation must have at least 2 events."""
        with pytest.raises(Exception):
            GeneratedConversation(
                provider="openai",
                platform="chrome",
                utility="trivial",
                events=[GeneratedEvent(event_type="user_message", content="hi")],
            )

    def test_valid_conversation_roundtrips(self):
        """A valid conversation serializes and deserializes cleanly."""
        conv = _fake_conversation()
        rebuilt = GeneratedConversation.model_validate(conv.model_dump())
        assert rebuilt == conv
        assert len(rebuilt.events) == 2


class TestGenerateSession:
    @patch("seerai.generate._write_to_firestore")
    @patch("seerai.generate.ask_llm")
    def test_calls_llm_with_description(self, mock_ask, mock_write):
        """The user's description is passed as the prompt to ask_llm."""
        mock_ask.return_value = _fake_conversation()
        generate_session("debug CORS", user_id="alice")
        prompt = mock_ask.call_args[0][0]
        assert "debug CORS" in prompt

    @patch("seerai.generate._write_to_firestore")
    @patch("seerai.generate.ask_llm")
    def test_provider_override(self, mock_ask, mock_write):
        """Caller-specified provider overrides the LLM's choice."""
        mock_ask.return_value = _fake_conversation(provider="google")
        result = generate_session("anything", user_id="alice", provider="openai")
        assert result.provider == "openai"

    @patch("seerai.generate._write_to_firestore")
    @patch("seerai.generate.ask_llm")
    def test_platform_override(self, mock_ask, mock_write):
        """Caller-specified platform overrides the LLM's choice."""
        mock_ask.return_value = _fake_conversation(platform="chrome")
        result = generate_session("anything", user_id="alice", platform="cli")
        assert result.platform == "cli"

    @patch("seerai.generate._write_to_firestore")
    @patch("seerai.generate.ask_llm")
    def test_dry_run_skips_write(self, mock_ask, mock_write):
        """write=False skips Firestore entirely."""
        mock_ask.return_value = _fake_conversation()
        generate_session("anything", user_id="alice", write=False)
        mock_write.assert_not_called()

    @patch("seerai.generate._write_to_firestore")
    @patch("seerai.generate.ask_llm")
    def test_writes_when_enabled(self, mock_ask, mock_write):
        """write=True (default) calls the Firestore writer."""
        conv = _fake_conversation()
        mock_ask.return_value = conv
        generate_session("anything", user_id="alice")
        mock_write.assert_called_once_with(conv, user_id="alice")

    @patch("seerai.generate._write_to_firestore")
    @patch("seerai.generate.ask_llm")
    def test_structured_output_type(self, mock_ask, mock_write):
        """ask_llm is called with response_type=GeneratedConversation."""
        mock_ask.return_value = _fake_conversation()
        generate_session("anything", user_id="alice")
        assert mock_ask.call_args[1]["response_type"] is GeneratedConversation


class TestWriteToFirestore:
    def test_writes_all_events_via_ingest(self):
        """Each generated event becomes an _write_event call with correct fields."""
        conv = _fake_conversation()
        mock_db = MagicMock()
        mock_batch = MagicMock()
        mock_db.batch.return_value = mock_batch

        with patch("seerai.firestore_client._client", mock_db):
            from seerai.generate import _write_to_firestore

            session_id = _write_to_firestore(conv, user_id="alice")

        assert isinstance(session_id, str)
        assert len(session_id) == 36  # UUID format
        # 2 events × 1 batch.commit each = 2 commits, plus 1 for utility
        assert mock_batch.commit.call_count == 2
