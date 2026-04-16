"""Generate realistic mock sessions using an LLM.

Uses covenance (multi-provider LLM lib) with structured output to produce
full conversations from a short description. Results are written to Firestore
via the existing ingest pipeline by default.

Two generation modes:
  - Plain (default): single conversation, no coach activity.
  - With intervention (--with-intervention): the LLM produces BOTH
    transcripts — the coached timeline (what the user actually saw) and
    the counterfactual (what they would have seen uncoached) — around a
    seeded mistake that the coach catches. Interventions can either
    flag-only (coach warns but the base answer stands; user may act on
    the warning in a later turn) or correct (base AI reads the coach
    message and revises its response). Both transcripts are written in
    a single generation to keep them internally consistent.

Usage as module:
    from seerai.generate import generate_session, generate_coached_session
    generate_session("user debugging a CORS issue", user_id="alice")
    generate_coached_session(
        "sales rep drafting compliance one-pager",
        user_id="rachel.martin",
        category="sources",
    )

Usage as CLI:
    uv run python -m seerai.generate "user debugging a CORS issue" --user alice
    uv run python -m seerai.generate "GDPR compliance questions" --user bob \\
        --with-intervention --category sources
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from seerai.entities import (
    CoachCategory,
    CoachKind,
    CoachMode,
    EventType,
    UtilityClass,
)

try:
    from covenance import ask_llm
except ImportError:
    ask_llm = None

PROVIDERS = ["anthropic", "openai", "google", "mistral"]
PLATFORMS = ["chrome", "firefox", "vscode", "cli", "slack", "safari"]

# Intervention outcome styles the generator can produce.
#   flag    — coach adds a warning inline; base AI keeps its original
#             answer but the user sees both and may revise course.
#   correct — base AI reads the coach message and writes a revised
#             answer in-place of the original draft.
InterventionStyle = Literal["flag", "correct"]


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


class GeneratedIntervention(BaseModel):
    """Coach intervention metadata the LLM emits alongside the transcripts.

    Mirrors the runtime CoachInterventionMetadata shape. The LLM fills in
    category/kind/mode/severity and a short rationale; timestamps and
    `targets_event_id` are wired up by the post-processor.
    """

    category: CoachCategory
    kind: CoachKind
    mode: CoachMode
    severity: int = Field(default=3, ge=1, le=5)
    rationale: str = Field(
        description="Coach's user-facing explanation — what was wrong and why."
    )
    quoted_span: str | None = Field(
        default=None,
        description="Exact text from the base AI draft that the coach flagged.",
    )
    sources: list[str] | None = Field(
        default=None, description="URLs / citations backing the correction."
    )
    estimated_savings_cents: int = Field(
        default=0, ge=0, description="Best-guess dollars (cents) this save is worth."
    )


class GeneratedCoachedConversation(BaseModel):
    """Both transcripts for one session where coach intervened.

    The LLM produces:
      - `coached_events`: what the user actually saw, with a
        coach_intervention event inserted at the intervention point.
      - `counterfactual_events`: what the user would have seen uncoached,
        starting from the same opening user_message and diverging at the
        mistake. Must start with the same user prompt as coached_events.
      - `intervention`: metadata for the single coach_intervention event.
      - `utility` + `counterfactual_utility`: post-hoc utility classes.
    """

    provider: str = Field(description=f"One of: {', '.join(PROVIDERS)}")
    platform: str = Field(description=f"One of: {', '.join(PLATFORMS)}")
    style: InterventionStyle = Field(
        description=(
            "flag = coach warns but base answer stands; "
            "correct = base AI reads the coach message and revises."
        )
    )
    utility: UtilityClass
    counterfactual_utility: UtilityClass
    intervention: GeneratedIntervention
    coached_events: list[GeneratedEvent] = Field(
        min_length=3,
        description=(
            "User-visible transcript. Must include exactly one "
            "coach_intervention event. For style=correct the AI turn that "
            "follows the coach message is the revised answer. For "
            "style=flag the AI's original answer precedes the coach "
            "message and may be followed by a user acknowledgement."
        ),
    )
    counterfactual_events: list[GeneratedEvent] = Field(
        min_length=2,
        description=(
            "Same opening user_message as coached_events, then the "
            "uncoached divergent path — the base AI's mistake is served, "
            "the user acts on it, and the consequences play out."
        ),
    )


SYSTEM_PROMPT = """\
Generate a realistic LLM chat conversation.
Return alternating user/AI turns. AI messages should include metadata with keys: model (string), tokens (int 50-800), latency_ms (int 200-3000).
Errors are rare — at most one per conversation, never first or last event."""


COACHED_SYSTEM_PROMPT = """\
You produce two parallel transcripts of the SAME chat session.

Scenario: a real-time "coach" LLM is observing the user's primary chat
with a base LLM. The base LLM makes a plausible, confident mistake —
factuality (wrong API / fabricated fact / math error), efficiency
(off-track drift / repeat failure / wrong tool), sources (fabricated
citation / misquoted source / weak source), or other (PII leak, wrong
scope, dangerous action). Coach intercepts.

TWO STYLES:
  - "correct": the base AI sees the coach message and writes a revised
    answer in place of the flawed one. The coached transcript shows:
    user turn → coach_intervention → revised AI turn (with metadata
    carrying `coached: true`, `pre_coach_content` set to the original
    draft text, `coach_intervention_ids` referencing the coach turn).
  - "flag": coach posts a warning, but the base AI's original answer
    stands. The coached transcript shows:
    user turn → original AI turn → coach_intervention → (optional
    user acknowledgement) → follow-up AI turn that factors in the warning.
    The original AI turn does NOT carry pre_coach_content.

REQUIREMENTS:
- coached_events and counterfactual_events MUST start with the same
  opening user_message (same content, same timestamp offset).
- The divergence point is the base AI's mistaken draft.
- Counterfactual shows the user acting on the mistake and the
  consequences (wasted time, wrong result, embarrassing rework, or in
  the PII case, PII being sent to the upstream provider).
- AI messages include metadata with `model` (string), `tokens`
  (50–800), `latency_ms` (200–3000). Use ONE model for all AI turns in
  a session.
- The coach_intervention event's `content` is the coach's user-facing
  rationale; keep it under ~400 chars, concrete, and concrete about
  what was wrong. DO NOT include metadata on the coach event — the
  post-processor fills metadata from the `intervention` field.
- utility = coached transcript class; counterfactual_utility =
  uncoached class. For the counterfactual expect harmful or trivial
  when the base mistake caused real waste.
- Errors (event_type="error") are rare; at most one, never first/last.
- Realism: pick concrete technologies / articles / code / customer
  names — not placeholders. The conversation should be believable.
"""


def generate_session(
    description: str,
    *,
    user_id: str,
    model: str = "claude-sonnet-4",
    provider: str | None = None,
    platform: str | None = None,
    write: bool = True,
) -> GeneratedConversation:
    """Generate a plain (uncoached) session.

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


def generate_coached_session(
    description: str,
    *,
    user_id: str,
    category: CoachCategory | None = None,
    style: InterventionStyle | None = None,
    model: str = "claude-sonnet-4",
    provider: str | None = None,
    platform: str | None = None,
    write: bool = True,
) -> tuple[GeneratedCoachedConversation, str]:
    """Generate a session with a coach intervention + counterfactual.

    Returns (conversation, session_id). The session is written to
    Firestore with `counterfactual_events` inlined on the Session doc
    and the coached events in the subcollection, matching the hero
    archetype shape.

    Args:
        description: Scenario prompt for the LLM (what the user is trying
            to do + the kind of mistake the base AI is prone to making).
        user_id: Target user.
        category: Pin the intervention category (factuality / efficiency
            / sources / other). LLM picks if None.
        style: "flag" or "correct". LLM picks if None.
    """
    if ask_llm is None:
        raise RuntimeError("Install covenance: pip install covenance")

    prompt_parts = [description]
    if category:
        prompt_parts.append(f"Intervention category must be: {category}.")
    if style:
        prompt_parts.append(f"Intervention style must be: {style}.")
    if provider:
        prompt_parts.append(f"Simulated LLM provider: {provider}.")
    if platform:
        prompt_parts.append(f"User platform: {platform}.")

    conversation = ask_llm(
        "\n".join(prompt_parts),
        model=model,
        response_type=GeneratedCoachedConversation,
        sys_msg=COACHED_SYSTEM_PROMPT,
    )

    if provider:
        conversation.provider = provider
    if platform:
        conversation.platform = platform

    session_id = ""
    if write:
        session_id = _write_coached_to_firestore(conversation, user_id=user_id)

    return conversation, session_id


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

    if conversation.utility:
        from seerai.entities import Session
        from seerai.firestore_client import get_firestore_client

        db = get_firestore_client()
        session_ref = Session._doc_ref(db, session_id, Session.parent_path(user_id))
        db.document(session_ref.path).set({"utility": conversation.utility}, merge=True)

    return session_id


def _write_coached_to_firestore(
    conversation: GeneratedCoachedConversation, *, user_id: str
) -> str:
    """Write a coached generated session to Firestore.

    Writes the coached events to the events subcollection, the counter-
    factual transcript inline on the session doc, and post-processes the
    coach_intervention event's metadata with the LLM-produced rationale
    and the runtime-wired fields (targets_event_id, accepted, savings).
    """
    from seerai.ingest.endpoint import _write_event
    from seerai.models import IngestEvent

    session_id = str(uuid.uuid4())
    now = datetime.now(UTC)

    # First pass: assign event_ids and timestamps to coached events so
    # the coach event's targets_event_id can be resolved.
    assigned: list[tuple[str, datetime, GeneratedEvent]] = []
    for i, event in enumerate(conversation.coached_events):
        assigned.append((str(uuid.uuid4()), now + timedelta(seconds=i * 30), event))

    # Locate the coach event and the AI turn it targets.
    coach_idx = next(
        (
            i
            for i, (_, _, ev) in enumerate(assigned)
            if ev.event_type == "coach_intervention"
        ),
        None,
    )
    if coach_idx is None:
        raise RuntimeError(
            "Generated coached transcript has no coach_intervention event."
        )

    if conversation.style == "correct":
        # Target is the AI turn AFTER the coach event (the revised one).
        target_idx = next(
            (
                i
                for i in range(coach_idx + 1, len(assigned))
                if assigned[i][2].event_type == "ai_message"
            ),
            None,
        )
    else:  # flag
        # Target is the AI turn BEFORE the coach event (the mistaken one).
        target_idx = next(
            (
                i
                for i in range(coach_idx - 1, -1, -1)
                if assigned[i][2].event_type == "ai_message"
            ),
            None,
        )
    if target_idx is None:
        raise RuntimeError(
            f"Could not locate target AI turn for style={conversation.style}"
        )

    target_event_id, _, target_event = assigned[target_idx]

    # Build the coach event's metadata from the generated intervention spec.
    intervention_md = {
        "category": conversation.intervention.category,
        "kind": conversation.intervention.kind,
        "mode": conversation.intervention.mode,
        "severity": conversation.intervention.severity,
        "targets_event_id": target_event_id,
        "quoted_span": conversation.intervention.quoted_span,
        "sources": conversation.intervention.sources,
        "accepted": True,
        "estimated_savings_cents": conversation.intervention.estimated_savings_cents,
    }

    # For style=correct, the target AI turn needs pre_coach_content set to
    # the original (flawed) draft. We use the counterfactual's first
    # AI-message content as the draft — it's the same turn the base AI
    # would have produced without coach.
    if conversation.style == "correct":
        draft = next(
            (
                ev.content
                for ev in conversation.counterfactual_events
                if ev.event_type == "ai_message"
            ),
            None,
        )
        if draft:
            md = target_event.metadata or {}
            md = dict(md)
            md["coached"] = True
            md["pre_coach_content"] = draft
            md["coach_intervention_ids"] = [assigned[coach_idx][0]]
            target_event.metadata = md

    # Bootstrap the User + Session docs via a single no-op ingest, then
    # write the events subcollection directly with deterministic event_ids
    # so the coach event's targets_event_id resolves.
    from seerai.entities import Event, Session
    from seerai.firestore_client import get_firestore_client as _fc

    # Seed the user + session parent docs with a single event (we'll
    # wipe the subcollection right after). We pick the first event from
    # the coached transcript; metadata/type don't matter since we
    # overwrite.
    _, first_ts, first_ev = assigned[0]
    _write_event(
        IngestEvent(
            user_id=user_id,
            session_id=session_id,
            event_type=first_ev.event_type,
            content=first_ev.content,
            timestamp=first_ts,
            metadata=first_ev.metadata,
            provider=conversation.provider,
            platform=conversation.platform,
        )
    )

    db = _fc()
    events_path = Event.parent_path(user_id, session_id)
    events_coll = db.document(events_path).collection("events")
    for doc in events_coll.stream():
        events_coll.document(doc.id).delete()

    for event_id, ts, event in assigned:
        metadata = event.metadata
        if event.event_type == "coach_intervention":
            metadata = intervention_md
        events_coll.document(event_id).set(
            {
                "event_id": event_id,
                "event_type": event.event_type,
                "content": event.content,
                "timestamp": ts,
                "metadata": metadata,
            }
        )

    # Session-level rollups + counterfactual transcript.
    counterfactual_events_doc = [
        {
            "event_id": str(uuid.uuid4()),
            "event_type": ev.event_type,
            "content": ev.content,
            "timestamp": now + timedelta(seconds=i * 30),
            "metadata": ev.metadata,
        }
        for i, ev in enumerate(conversation.counterfactual_events)
    ]
    # First event of counterfactual must share content with first event of
    # coached (same opening user_message). We enforce that here in case
    # the LLM slightly deviated on whitespace.
    if counterfactual_events_doc and assigned:
        counterfactual_events_doc[0]["content"] = assigned[0][2].content

    # Recompute session rollups: we bypassed _write_event's per-event
    # accumulators, so set them explicitly from the rewritten subcollection.
    last_ts = assigned[-1][1]
    last_type = assigned[-1][2].event_type
    error_count = sum(1 for _, _, ev in assigned if ev.event_type == "error")
    token_usage: dict[str, int] = {}
    for _, _, ev in assigned:
        if ev.event_type == "ai_message" and ev.metadata:
            model_name = ev.metadata.get("model")
            tokens = ev.metadata.get("tokens")
            if model_name and tokens:
                token_usage[model_name] = token_usage.get(model_name, 0) + int(tokens)

    session_ref = Session._doc_ref(db, session_id, Session.parent_path(user_id))
    session_updates = {
        "session_id": session_id,
        "user_id": user_id,
        "provider": conversation.provider,
        "platform": conversation.platform,
        "last_event_at": last_ts,
        "last_event_type": last_type,
        "event_count": len(assigned),
        "error_count": error_count,
        "token_usage": token_usage or None,
        "utility": conversation.utility,
        "counterfactual_utility": conversation.counterfactual_utility,
        "counterfactual_events": counterfactual_events_doc,
        "intervention_count": 1,
        "intervention_categories": [conversation.intervention.category],
    }
    db.document(session_ref.path).set(session_updates, merge=True)

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
    parser.add_argument(
        "--with-intervention",
        action="store_true",
        help="Generate a coached session with counterfactual.",
    )
    parser.add_argument(
        "--category",
        choices=["factuality", "efficiency", "sources", "other"],
        help="Pin intervention category (coached mode).",
    )
    parser.add_argument(
        "--style",
        choices=["flag", "correct"],
        help="Pin intervention style (coached mode).",
    )
    args = parser.parse_args()

    if args.with_intervention:
        conversation, session_id = generate_coached_session(
            args.description,
            user_id=args.user,
            category=args.category,
            style=args.style,
            model=args.model,
            provider=args.provider,
            platform=args.platform,
            write=not args.dry_run,
        )
        print(f"Provider:      {conversation.provider}")
        print(f"Platform:      {conversation.platform}")
        print(f"Style:         {conversation.style}")
        print(
            f"Utility:       {conversation.utility} "
            f"(counterfactual: {conversation.counterfactual_utility})"
        )
        print(
            f"Intervention:  {conversation.intervention.category} / "
            f"{conversation.intervention.kind} / {conversation.intervention.mode}"
        )
        print(f"Coached turns:        {len(conversation.coached_events)}")
        print(f"Counterfactual turns: {len(conversation.counterfactual_events)}")
        for label, stream in (
            ("COACHED", conversation.coached_events),
            ("COUNTERFACTUAL", conversation.counterfactual_events),
        ):
            print(f"\n=== {label} ===")
            for i, ev in enumerate(stream):
                tag = {
                    "user_message": "USER",
                    "ai_message": "AI",
                    "coach_intervention": "COACH",
                    "error": "ERR",
                }[ev.event_type]
                preview = ev.content[:80] + ("..." if len(ev.content) > 80 else "")
                print(f"  [{i}] {tag}: {preview}")
        if not args.dry_run:
            print(f"\nsession_id: {session_id}")
        else:
            print("\n(dry run — nothing written)")
        return

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
