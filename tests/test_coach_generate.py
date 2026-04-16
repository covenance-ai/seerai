"""Tests for the coached-session generator path.

Uses a monkeypatched `ask_llm` so the test exercises the full write
pipeline (event_id wiring, counterfactual inlining, session rollups)
without requiring a live LLM call. Writes go to an isolated LocalStore
in a tmp dir — the committed snapshot is untouched.
"""

from __future__ import annotations

import pytest

from seerai import firestore_client as fc
from seerai import generate as gen
from seerai.entities import Event, Session
from seerai.local_client import LocalStore
from seerai.plausibility import CoachInterventionIntegrity


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Swap the process-wide firestore client for a throwaway LocalStore.

    Every test in this module writes through the generator, and we do NOT
    want those writes landing in data/snapshot.json. This fixture seeds
    a minimal user doc so _write_event can attach sessions.
    """
    store = LocalStore(tmp_path / "snapshot.json")
    store.data["users"] = {
        "alice.johnson": {
            "user_id": "alice.johnson",
            "last_active": "2026-01-01T00:00:00+00:00",
        }
    }
    monkeypatch.setattr(fc, "_client", store)
    monkeypatch.setattr(fc, "_source", "local")
    yield store


def _fake_coached_conversation(style: str = "correct"):
    """Build a minimal GeneratedCoachedConversation by hand."""
    return gen.GeneratedCoachedConversation(
        provider="anthropic",
        platform="vscode",
        style=style,
        utility="useful",
        counterfactual_utility="harmful",
        intervention=gen.GeneratedIntervention(
            category="factuality",
            kind="hallucinated_api",
            mode="rewrite",
            severity=2,
            rationale="Rewrote a nonexistent API call.",
            quoted_span="df.nonexistent_method()",
            sources=["https://example.com/docs"],
            estimated_savings_cents=2500,
        ),
        coached_events=(
            [
                gen.GeneratedEvent(event_type="user_message", content="How do I Z?"),
                gen.GeneratedEvent(
                    event_type="coach_intervention",
                    content="Caught a hallucinated API in the drafted answer.",
                ),
                gen.GeneratedEvent(
                    event_type="ai_message",
                    content="Use the real API: df.real_method().",
                    metadata={
                        "model": "claude-sonnet-4",
                        "tokens": 120,
                        "latency_ms": 900,
                    },
                ),
            ]
            if style == "correct"
            else [
                gen.GeneratedEvent(event_type="user_message", content="How do I Z?"),
                gen.GeneratedEvent(
                    event_type="ai_message",
                    content="Try df.nonexistent_method()",
                    metadata={
                        "model": "claude-sonnet-4",
                        "tokens": 60,
                        "latency_ms": 500,
                    },
                ),
                gen.GeneratedEvent(
                    event_type="coach_intervention",
                    content="That method does not exist; recommend df.real_method().",
                ),
                gen.GeneratedEvent(
                    event_type="user_message", content="Thanks — trying real_method."
                ),
                gen.GeneratedEvent(
                    event_type="ai_message",
                    content="Good — df.real_method() is the right call.",
                    metadata={
                        "model": "claude-sonnet-4",
                        "tokens": 40,
                        "latency_ms": 400,
                    },
                ),
            ]
        ),
        counterfactual_events=[
            gen.GeneratedEvent(event_type="user_message", content="How do I Z?"),
            gen.GeneratedEvent(
                event_type="ai_message",
                content="Try df.nonexistent_method()",
                metadata={"model": "claude-sonnet-4", "tokens": 60, "latency_ms": 500},
            ),
            gen.GeneratedEvent(
                event_type="user_message",
                content="AttributeError — no such method.",
            ),
            gen.GeneratedEvent(
                event_type="ai_message",
                content="Apologies — use df.real_method() instead.",
                metadata={"model": "claude-sonnet-4", "tokens": 50, "latency_ms": 400},
            ),
        ],
    )


@pytest.fixture
def mock_ask_llm(monkeypatch):
    """Monkeypatch covenance.ask_llm to return a synthetic coached conversation."""

    holder = {"conv": _fake_coached_conversation("correct")}

    def fake(prompt, *, model, response_type, sys_msg):
        # Only valid for the coached path in these tests.
        assert response_type is gen.GeneratedCoachedConversation
        return holder["conv"]

    monkeypatch.setattr(gen, "ask_llm", fake)
    return holder


class TestCoachedGenerator:
    def test_correct_style_writes_both_transcripts(self, mock_ask_llm):
        mock_ask_llm["conv"] = _fake_coached_conversation("correct")
        conv, sid = gen.generate_coached_session(
            "hallucinated API scenario", user_id="alice.johnson"
        )
        assert sid

        session = Session.get(sid, parent_path=Session.parent_path("alice.johnson"))
        assert session is not None
        assert session.utility == "useful"
        assert session.counterfactual_utility == "harmful"
        assert session.intervention_count == 1
        assert session.intervention_categories == ["factuality"]
        assert session.counterfactual_events
        assert len(session.counterfactual_events) == 4

    def test_coach_event_targets_a_real_ai_event(self, mock_ask_llm):
        """The coach's targets_event_id must resolve to an AI event in the session."""
        mock_ask_llm["conv"] = _fake_coached_conversation("correct")
        _, sid = gen.generate_coached_session(
            "factuality scenario", user_id="alice.johnson"
        )

        events = Event.for_session("alice.johnson", sid)
        by_id = {e.event_id: e for e in events}
        coach = next(e for e in events if e.event_type == "coach_intervention")
        target_id = coach.metadata["targets_event_id"]
        assert target_id in by_id
        assert by_id[target_id].event_type == "ai_message"

    def test_correct_style_sets_pre_coach_content_on_target(self, mock_ask_llm):
        """style=correct means the target AI bubble carries the original draft."""
        mock_ask_llm["conv"] = _fake_coached_conversation("correct")
        _, sid = gen.generate_coached_session(
            "factuality scenario", user_id="alice.johnson"
        )
        events = Event.for_session("alice.johnson", sid)
        by_id = {e.event_id: e for e in events}
        coach = next(e for e in events if e.event_type == "coach_intervention")
        target = by_id[coach.metadata["targets_event_id"]]
        assert target.metadata.get("coached") is True
        assert target.metadata.get("pre_coach_content")

    def test_flag_style_targets_the_prior_ai_turn(self, mock_ask_llm):
        """style=flag means coach targets the mistaken AI turn that precedes it."""
        mock_ask_llm["conv"] = _fake_coached_conversation("flag")
        _, sid = gen.generate_coached_session(
            "flag-only scenario", user_id="alice.johnson"
        )
        events = Event.for_session("alice.johnson", sid)
        events.sort(key=lambda e: e.timestamp)
        coach_idx = next(
            i for i, e in enumerate(events) if e.event_type == "coach_intervention"
        )
        target_id = events[coach_idx].metadata["targets_event_id"]
        # Target must be at an earlier index than the coach event.
        target_idx = next(i for i, e in enumerate(events) if e.event_id == target_id)
        assert target_idx < coach_idx

    def test_generated_session_counterfactual_shares_opening_prompt(self, mock_ask_llm):
        """Counterfactual's first event must match the coached transcript's first."""
        mock_ask_llm["conv"] = _fake_coached_conversation("correct")
        _, sid = gen.generate_coached_session(
            "factuality scenario", user_id="alice.johnson"
        )
        session = Session.get(sid, parent_path=Session.parent_path("alice.johnson"))
        events = Event.for_session("alice.johnson", sid)
        events.sort(key=lambda e: e.timestamp)
        first_coached = events[0]
        first_cf = session.counterfactual_events[0]
        assert first_coached.content == first_cf.content
        assert first_coached.event_type == first_cf.event_type == "user_message"


class TestGeneratedSessionPassesIntegrity:
    """Regression: the generator's output must satisfy CoachInterventionIntegrity."""

    def test_generated_session_alone_is_clean(self, mock_ask_llm, isolated_store):
        """Build a tiny snapshot around one generated session and run the integrity check."""
        mock_ask_llm["conv"] = _fake_coached_conversation("correct")
        _, sid = gen.generate_coached_session(
            "factuality scenario", user_id="alice.johnson"
        )

        data = isolated_store.data
        violations = CoachInterventionIntegrity().violations(data)
        # Filter to the newly-generated session only (pre-existing heroes
        # already proven clean).
        mine = [v for v in violations if sid in v.path]
        assert mine == []
