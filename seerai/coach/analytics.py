"""Aggregations over coach interventions across the org.

Pure functions over the existing User / Session / Event entities. Used by
the /api/coach endpoints and the /exec/coach dashboard. Designed to be
called per-request — for the demo dataset (a few hundred sessions) the
cost is negligible; if it ever isn't, cache at the endpoint layer.

The shape of every aggregate result mirrors the UX framing: every metric
gets a `with_coach` value, a `without_coach` value, and a `delta`. The
delta is the *value coach added*, computed against the counterfactual we
stored at session ingest.
"""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel

from seerai.entities import (
    CoachCategory,
    Event,
    OrgNode,
    Session,
    User,
    UtilityClass,
)

# ─── Per-class utility valuation ───────────────────────────────────────
#
# Cents-per-session value priors. Tuneable. Used to translate utility
# class shifts (counterfactual_utility -> utility) into a $ delta. Hybrid
# pricing as agreed: utility shift carries the main value signal; a
# per-intervention efficiency prior is added on top only when the utility
# class didn't change but the conversation got materially shorter.
UTILITY_VALUE_CENTS: dict[str, int] = {
    "harmful": -3000,  # net-negative session
    "non_work": 0,
    "trivial": 500,
    "useful": 5000,
}

# Cents added to the delta for an efficiency-category intervention when
# utility class is unchanged (already useful) but the coach saved turns.
EFFICIENCY_RESCUE_CENTS = 1500


# ─── Result types ──────────────────────────────────────────────────────


class Compared(BaseModel):
    """Three-value KPI: without-coach, with-coach, and the delta."""

    without_coach: float
    with_coach: float
    delta: float


class CategoryBreakdown(BaseModel):
    category: CoachCategory
    interventions: int
    accepted: int
    estimated_savings_cents: int


class UtilityShift(BaseModel):
    """How many sessions moved from `from_class` to `to_class` thanks to coach."""

    from_class: UtilityClass
    to_class: UtilityClass
    sessions: int


class CoachSummary(BaseModel):
    """Aggregate coach impact across the filter scope.

    `sessions_observed` counts every session in scope (coached and not);
    `coached_sessions` counts only those with at least one intervention.
    The KPI fields below are always computed across all observed sessions
    so that aggregate ratios are meaningful (a coach that fires on 5% of
    sessions but rescues every one of them should still be readable).
    """

    sessions_observed: int
    coached_sessions: int
    interventions_total: int
    interventions_accepted: int
    acceptance_rate: float  # 0..1, 0 if no interventions with explicit accept signal
    estimated_savings_cents: int

    # Per-category and per-kind tallies.
    by_category: list[CategoryBreakdown]
    by_kind: dict[str, int]
    by_mode: dict[str, int]

    # Utility-class redistribution: how the with-coach distribution of
    # session utility differs from the without-coach (counterfactual)
    # distribution. Each KPI is value-weighted via UTILITY_VALUE_CENTS.
    utility_distribution_with: dict[str, int]
    utility_distribution_without: dict[str, int]
    utility_shifts: list[UtilityShift]

    # Three-way KPIs ready for direct rendering.
    value_cents: Compared
    turns: Compared


class CoachFeedItem(BaseModel):
    """One intervention surfaced in the cross-org coach feed."""

    intervention_id: str
    user_id: str
    session_id: str
    org_id: str | None
    timestamp: str  # ISO
    category: CoachCategory
    kind: str
    mode: str
    severity: int
    content: str
    quoted_span: str | None
    sources: list[str] | None
    accepted: bool | None
    estimated_savings_cents: int


# ─── Iteration helpers ─────────────────────────────────────────────────


def _users_in_scope(*, user_id: str | None, org_id: str | None) -> list[User]:
    if user_id:
        u = User.get(user_id)
        return [u] if u else []
    users = User.list(order_by=None, limit=0)
    if org_id:
        descendants = {
            n.org_id for n in OrgNode.query("path", "array_contains", org_id)
        }
        users = [u for u in users if u.org_id in descendants]
    return users


def _sessions_for(user_id: str) -> list[Session]:
    return Session.for_user(user_id, limit=0)


def _coach_events(uid: str, sid: str) -> list[Event]:
    return [
        e for e in Event.for_session(uid, sid) if e.event_type == "coach_intervention"
    ]


# ─── Aggregations ──────────────────────────────────────────────────────


def coach_summary(
    *,
    user_id: str | None = None,
    org_id: str | None = None,
    category: CoachCategory | None = None,
) -> CoachSummary:
    """Compute the cross-session coach impact summary for the filter scope."""

    users = _users_in_scope(user_id=user_id, org_id=org_id)

    sessions_observed = 0
    coached_sessions = 0
    intervention_total = 0
    intervention_accepted = 0
    intervention_with_accept_signal = 0
    estimated_savings = 0

    by_category_counts: Counter[str] = Counter()
    by_category_accepted: Counter[str] = Counter()
    by_category_savings: Counter[str] = Counter()
    by_kind: Counter[str] = Counter()
    by_mode: Counter[str] = Counter()

    util_with: Counter[str] = Counter()
    util_without: Counter[str] = Counter()
    shift_counts: Counter[tuple[str, str]] = Counter()
    value_with_cents = 0
    value_without_cents = 0

    turns_with = 0
    turns_without = 0
    # Per-session turns_saved is clamped at zero — when coach blocks/redacts
    # without changing trajectory length, value comes from compliance or
    # correctness, not from saved turns. Subtracting those would misread the
    # PII / source-correction wins as "coach added work."
    turns_saved = 0

    for user in users:
        for session in _sessions_for(user.user_id):
            sessions_observed += 1

            # Per-session utility delta: contributes to the value KPI even
            # when the session has no interventions (delta is 0 there).
            actual_util = session.utility or "non_work"
            cf_util = session.counterfactual_utility or actual_util
            util_with[actual_util] += 1
            util_without[cf_util] += 1
            value_with_cents += UTILITY_VALUE_CENTS.get(actual_util, 0)
            value_without_cents += UTILITY_VALUE_CENTS.get(cf_util, 0)

            # Turn counts: the actual session has `event_count` turns; the
            # counterfactual transcript (if present) has its own length.
            actual_turns = session.event_count
            cf_turns = (
                len(session.counterfactual_events)
                if session.counterfactual_events
                else actual_turns
            )
            turns_with += actual_turns
            turns_without += cf_turns
            turns_saved += max(0, cf_turns - actual_turns)

            if not session.intervention_count:
                continue

            for ev in _coach_events(user.user_id, session.session_id):
                md = ev.metadata or {}
                ev_cat = md.get("category")
                if category and ev_cat != category:
                    continue

                if ev_cat:
                    by_category_counts[ev_cat] += 1
                if k := md.get("kind"):
                    by_kind[k] += 1
                if m := md.get("mode"):
                    by_mode[m] += 1
                accepted = md.get("accepted")
                if accepted is not None:
                    intervention_with_accept_signal += 1
                    if accepted:
                        intervention_accepted += 1
                        if ev_cat:
                            by_category_accepted[ev_cat] += 1
                savings = int(md.get("estimated_savings_cents") or 0)
                estimated_savings += savings
                if ev_cat:
                    by_category_savings[ev_cat] += savings
                intervention_total += 1

            # Apply efficiency-rescue prior when utility class didn't change
            # but the coach materially shortened the conversation.
            if (
                actual_util == cf_util
                and "efficiency" in (session.intervention_categories or [])
                and cf_turns > actual_turns
            ):
                value_with_cents += EFFICIENCY_RESCUE_CENTS

            if session.intervention_count > 0:
                coached_sessions += 1
            if actual_util != cf_util:
                shift_counts[(cf_util, actual_util)] += 1

    by_category = [
        CategoryBreakdown(
            category=cat,
            interventions=by_category_counts[cat],
            accepted=by_category_accepted[cat],
            estimated_savings_cents=by_category_savings[cat],
        )
        for cat in sorted(by_category_counts)
    ]

    acceptance_rate = (
        intervention_accepted / intervention_with_accept_signal
        if intervention_with_accept_signal
        else 0.0
    )

    utility_shifts = [
        UtilityShift(from_class=fr, to_class=to, sessions=n)
        for (fr, to), n in sorted(shift_counts.items(), key=lambda kv: -kv[1])
    ]

    return CoachSummary(
        sessions_observed=sessions_observed,
        coached_sessions=coached_sessions,
        interventions_total=intervention_total,
        interventions_accepted=intervention_accepted,
        acceptance_rate=acceptance_rate,
        estimated_savings_cents=estimated_savings,
        by_category=by_category,
        by_kind=dict(by_kind),
        by_mode=dict(by_mode),
        utility_distribution_with=dict(util_with),
        utility_distribution_without=dict(util_without),
        utility_shifts=utility_shifts,
        value_cents=Compared(
            without_coach=value_without_cents,
            with_coach=value_with_cents,
            delta=value_with_cents - value_without_cents,
        ),
        turns=Compared(
            without_coach=turns_without,
            with_coach=turns_with,
            delta=turns_saved,  # clamped: per-session max(0, cf - actual)
        ),
    )


def coach_feed(
    *,
    user_id: str | None = None,
    org_id: str | None = None,
    category: CoachCategory | None = None,
    limit: int = 50,
) -> list[CoachFeedItem]:
    """Most recent interventions across the filter scope, newest first."""

    users = _users_in_scope(user_id=user_id, org_id=org_id)
    items: list[CoachFeedItem] = []

    for user in users:
        for session in _sessions_for(user.user_id):
            if not session.intervention_count:
                continue
            for ev in _coach_events(user.user_id, session.session_id):
                md = ev.metadata or {}
                ev_cat = md.get("category") or "other"
                if category and ev_cat != category:
                    continue
                items.append(
                    CoachFeedItem(
                        intervention_id=ev.event_id,
                        user_id=user.user_id,
                        session_id=session.session_id,
                        org_id=user.org_id,
                        timestamp=ev.timestamp.isoformat(),
                        category=ev_cat,
                        kind=md.get("kind", ""),
                        mode=md.get("mode", ""),
                        severity=int(md.get("severity") or 3),
                        content=ev.content,
                        quoted_span=md.get("quoted_span"),
                        sources=md.get("sources"),
                        accepted=md.get("accepted"),
                        estimated_savings_cents=int(
                            md.get("estimated_savings_cents") or 0
                        ),
                    )
                )

    items.sort(key=lambda x: x.timestamp, reverse=True)
    return items[:limit] if limit else items
