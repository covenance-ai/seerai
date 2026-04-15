"""Generate realistic mock sessions using an LLM.

Uses covenance (multi-provider LLM lib) with structured output to produce
full conversations from a short description. Results are written to Firestore
via the existing ingest pipeline by default.

Usage as module:
    from seerai.generate import generate_session
    session = generate_session("user debugging a CORS issue", user_id="alice")

Usage as CLI:
    uv run python -m seerai.generate "user debugging a CORS issue" --user alice
    uv run python -m seerai.generate "GDPR compliance questions" --user bob --model gpt-4o --dry-run
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field

from seerai.entities import EventType, UtilityClass

try:
    from covenance import ask_llm
except ImportError:
    ask_llm = None

PROVIDERS = ["anthropic", "openai", "google", "mistral"]
PLATFORMS = ["chrome", "firefox", "vscode", "cli", "slack", "safari"]


class GeneratedEvent(BaseModel):
    """A single conversation turn produced by the LLM."""

    event_type: EventType
    content: str
    metadata: dict | None = None


class GeneratedConversation(BaseModel):
    """Full conversation output from the LLM.

    The LLM fills in provider/platform/utility based on context,
    and generates a realistic sequence of events.
    """

    provider: str = Field(description=f"One of: {', '.join(PROVIDERS)}")
    platform: str = Field(description=f"One of: {', '.join(PLATFORMS)}")
    utility: UtilityClass = Field(description="How useful was this session to the user")
    events: list[GeneratedEvent] = Field(
        min_length=2,
        description="Alternating user_message / ai_message turns. May include occasional error events.",
    )


SYSTEM_PROMPT = """\
Generate a realistic LLM chat conversation.
Return alternating user/AI turns. AI messages should include metadata with keys: model (string), tokens (int 50-800), latency_ms (int 200-3000).
Errors are rare — at most one per conversation, never first or last event."""


def generate_session(
    description: str,
    *,
    user_id: str,
    model: str = "claude-sonnet-4",
    provider: str | None = None,
    platform: str | None = None,
    write: bool = True,
) -> GeneratedConversation:
    """Generate a session from a description and optionally write it to Firestore.

    Args:
        description: What the conversation is about.
        user_id: Target user to attach the session to.
        model: LLM model to use for generation.
        provider: Override the simulated provider (LLM picks if None).
        platform: Override the simulated platform (LLM picks if None).
        write: If True, write the session to Firestore via ingest.
    """
    if ask_llm is None:
        raise RuntimeError("Install covenance: pip install covenance")

    prompt = description
    if provider:
        prompt += f"\nThe LLM provider is: {provider}"
    if platform:
        prompt += f"\nThe user's platform is: {platform}"

    conversation = ask_llm(
        prompt, model=model, response_type=GeneratedConversation, sys_msg=SYSTEM_PROMPT
    )

    if provider:
        conversation.provider = provider
    if platform:
        conversation.platform = platform

    if write:
        _write_to_firestore(conversation, user_id=user_id)

    return conversation


def _write_to_firestore(conversation: GeneratedConversation, *, user_id: str) -> str:
    """Write a generated conversation to Firestore. Returns the session_id."""
    from seerai.ingest.endpoint import _write_event
    from seerai.models import IngestEvent

    session_id = str(uuid.uuid4())
    now = datetime.now(UTC)

    for i, event in enumerate(conversation.events):
        ts = now + timedelta(seconds=i * 30)
        _write_event(
            IngestEvent(
                user_id=user_id,
                session_id=session_id,
                event_type=event.event_type,
                content=event.content,
                timestamp=ts,
                metadata=event.metadata,
                provider=conversation.provider,
                platform=conversation.platform,
            )
        )

    # Write utility separately (not on IngestEvent)
    if conversation.utility:
        from seerai.entities import Session
        from seerai.firestore_client import get_firestore_client

        db = get_firestore_client()
        session_ref = Session._doc_ref(db, session_id, Session.parent_path(user_id))
        db.document(session_ref.path).set({"utility": conversation.utility}, merge=True)

    return session_id


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate a mock session via LLM")
    parser.add_argument("description", help="Short description of the session")
    parser.add_argument("--user", required=True, help="Target user_id")
    parser.add_argument("--model", default="claude-sonnet-4", help="Generator model")
    parser.add_argument("--provider", help="Override simulated provider")
    parser.add_argument("--platform", help="Override simulated platform")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print conversation without writing"
    )
    args = parser.parse_args()

    conversation = generate_session(
        args.description,
        user_id=args.user,
        model=args.model,
        provider=args.provider,
        platform=args.platform,
        write=not args.dry_run,
    )

    print(f"Provider: {conversation.provider}")
    print(f"Platform: {conversation.platform}")
    print(f"Utility:  {conversation.utility}")
    print(f"Events:   {len(conversation.events)}")
    for i, ev in enumerate(conversation.events):
        label = {"user_message": "USER", "ai_message": "AI", "error": "ERR"}[
            ev.event_type
        ]
        preview = ev.content[:80] + ("..." if len(ev.content) > 80 else "")
        print(f"  [{i}] {label}: {preview}")

    if args.dry_run:
        print("\n(dry run — nothing written)")


if __name__ == "__main__":
    main()
