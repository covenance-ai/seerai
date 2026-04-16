"""Plausibility checks and normalization for local snapshot data.

Each check pairs a violation detector with a normalization strategy:
  - violations(data) finds issues
  - normalize(data) mutates data in place, returns fix count

Usage:
    python -m seerai.plausibility          # report violations
    python -m seerai.plausibility --fix    # normalize in-place
"""

from __future__ import annotations

import json
import random
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

SNAPSHOT_PATH = Path(__file__).parent.parent / "data" / "snapshot.json"

PROVIDER_MODELS = {
    "anthropic": ["claude-sonnet-4", "claude-haiku-4"],
    "openai": ["gpt-4o", "o3-mini"],
    "google": ["gemini-2.0-flash", "gemini-2.5-pro"],
    "mistral": ["mistral-large", "mistral-small"],
}

SUBSCRIPTION_PLANS: dict[str, tuple[str, int]] = {
    "anthropic": ("Claude Pro", 2000),
    "openai": ("ChatGPT Plus", 2000),
    "google": ("Gemini Advanced", 2000),
    "mistral": ("Le Chat Pro", 1500),
}


@dataclass
class Violation:
    check: str
    path: str
    message: str

    def __str__(self):
        return f"[{self.check}] {self.path}: {self.message}"


# ── helpers ──────────────────────────────────────────────────────────────


def _user_subscriptions(data: dict) -> dict[str, set[str]]:
    """Map user_id -> set of subscribed provider names."""
    out: dict[str, set[str]] = {}
    for sub in data.get("subscriptions", {}).values():
        out.setdefault(sub["user_id"], set()).add(sub["provider"])
    return out


def _session_keys(data: dict) -> list[str]:
    """All top-level keys shaped 'users/{uid}/sessions'."""
    return [
        k
        for k in data
        if k.startswith("users/") and k.endswith("/sessions") and k.count("/") == 2
    ]


def _events_key(uid: str, sid: str) -> str:
    return f"users/{uid}/sessions/{sid}/events"


def _sorted_events(events: dict) -> list[tuple[str, dict]]:
    """(event_id, event_dict) pairs sorted by timestamp."""
    return sorted(events.items(), key=lambda kv: kv[1]["timestamp"])


# ── check base ───────────────────────────────────────────────────────────


class Check:
    """A plausibility check with an optional normalization strategy."""

    name: str = ""

    def violations(self, data: dict) -> list[Violation]:
        raise NotImplementedError

    def normalize(self, data: dict) -> int:
        """Fix violations in-place. Returns count of fixes."""
        raise NotImplementedError


# ── concrete checks (order matters — see ALL_CHECKS) ─────────────────────


class SubscriptionCoverage(Check):
    """Every user with sessions must have at least one active subscription."""

    name = "subscription_coverage"

    def violations(self, data):
        user_subs = _user_subscriptions(data)
        out = []
        for key in _session_keys(data):
            uid = key.split("/")[1]
            if data[key] and uid not in user_subs:
                out.append(
                    Violation(
                        self.name,
                        f"users/{uid}",
                        f"{len(data[key])} sessions, no subscription",
                    )
                )
        return out

    def normalize(self, data):
        """Add subscriptions matching providers the user actually uses."""
        user_subs = _user_subscriptions(data)
        fixed = 0
        for key in _session_keys(data):
            uid = key.split("/")[1]
            if not data[key] or uid in user_subs:
                continue
            used = {s["provider"] for s in data[key].values() if s.get("provider")}
            for provider in used:
                if provider not in SUBSCRIPTION_PLANS:
                    continue
                plan_name, cost = SUBSCRIPTION_PLANS[provider]
                sub_id = str(uuid.uuid4())
                started = datetime.now(UTC) - timedelta(days=random.randint(30, 180))
                data.setdefault("subscriptions", {})[sub_id] = {
                    "subscription_id": sub_id,
                    "user_id": uid,
                    "provider": provider,
                    "plan": plan_name,
                    "monthly_cost_cents": cost,
                    "currency": "USD",
                    "started_at": started.isoformat(),
                    "ended_at": None,
                }
            fixed += 1
        return fixed


class ProviderMatch(Check):
    """Session provider must be one the user is subscribed to."""

    name = "provider_match"

    def violations(self, data):
        user_subs = _user_subscriptions(data)
        out = []
        for key in _session_keys(data):
            uid = key.split("/")[1]
            sub_provs = user_subs.get(uid, set())
            for sid, session in data[key].items():
                p = session.get("provider")
                if p and p not in sub_provs:
                    out.append(
                        Violation(
                            self.name,
                            f"users/{uid}/sessions/{sid}",
                            f"provider={p}, subscribed={sub_provs}",
                        )
                    )
        return out

    def normalize(self, data):
        """Reassign session provider to a subscribed one; fix event models."""
        user_subs = _user_subscriptions(data)
        fixed = 0
        for key in _session_keys(data):
            uid = key.split("/")[1]
            sub_provs = sorted(user_subs.get(uid, set()))
            if not sub_provs:
                continue
            for sid, session in data[key].items():
                p = session.get("provider")
                if p and p not in sub_provs:
                    new_prov = random.choice(sub_provs)
                    session["provider"] = new_prov
                    ek = _events_key(uid, sid)
                    if ek in data:
                        new_model = random.choice(PROVIDER_MODELS[new_prov])
                        for event in data[ek].values():
                            md = event.get("metadata")
                            if md and "model" in md:
                                md["model"] = new_model
                    fixed += 1
        return fixed


class SessionEndsOnAI(Check):
    """Sessions must not end on a user_message."""

    name = "session_ends_on_ai"

    def violations(self, data):
        out = []
        for key in _session_keys(data):
            uid = key.split("/")[1]
            for sid, session in data[key].items():
                ek = _events_key(uid, sid)
                if ek in data and data[ek]:
                    events = _sorted_events(data[ek])
                    if events[-1][1]["event_type"] == "user_message":
                        out.append(
                            Violation(
                                self.name,
                                f"users/{uid}/sessions/{sid}",
                                "last event is user_message",
                            )
                        )
                elif session.get("last_event_type") == "user_message":
                    out.append(
                        Violation(
                            self.name,
                            f"users/{uid}/sessions/{sid}",
                            "last_event_type is user_message (stub)",
                        )
                    )
        return out

    def normalize(self, data):
        """Remove trailing user_message from full sessions; fix stub field."""
        fixed = 0
        for key in _session_keys(data):
            uid = key.split("/")[1]
            for sid, session in data[key].items():
                ek = _events_key(uid, sid)
                if ek in data and data[ek]:
                    events = _sorted_events(data[ek])
                    if events[-1][1]["event_type"] == "user_message":
                        del data[ek][events[-1][0]]
                        remaining = _sorted_events(data[ek])
                        if remaining:
                            session["last_event_type"] = remaining[-1][1]["event_type"]
                            session["last_event_at"] = remaining[-1][1]["timestamp"]
                            session["event_count"] = len(remaining)
                        fixed += 1
                elif session.get("last_event_type") == "user_message":
                    session["last_event_type"] = "ai_message"
                    fixed += 1
        return fixed


class SessionStartsWithUser(Check):
    """First event in a session must be a user_message."""

    name = "session_starts_with_user"

    def violations(self, data):
        out = []
        for key in _session_keys(data):
            uid = key.split("/")[1]
            for sid, _ in data[key].items():
                ek = _events_key(uid, sid)
                if ek not in data or not data[ek]:
                    continue
                events = _sorted_events(data[ek])
                if events[0][1]["event_type"] != "user_message":
                    out.append(
                        Violation(
                            self.name,
                            f"users/{uid}/sessions/{sid}",
                            f"starts with {events[0][1]['event_type']}",
                        )
                    )
        return out

    def normalize(self, data):
        """Drop leading non-user events."""
        fixed = 0
        for key in _session_keys(data):
            uid = key.split("/")[1]
            for sid, session in data[key].items():
                ek = _events_key(uid, sid)
                if ek not in data or not data[ek]:
                    continue
                events = _sorted_events(data[ek])
                removed = 0
                while events and events[0][1]["event_type"] != "user_message":
                    del data[ek][events[0][0]]
                    events.pop(0)
                    removed += 1
                if removed:
                    session["event_count"] = len(data[ek])
                    fixed += 1
        return fixed


class SingleModelPerSession(Check):
    """All AI messages within a session must use the same model."""

    name = "single_model_per_session"

    def violations(self, data):
        out = []
        for key in _session_keys(data):
            uid = key.split("/")[1]
            for sid, _ in data[key].items():
                ek = _events_key(uid, sid)
                if ek not in data:
                    continue
                models = {
                    e["metadata"]["model"]
                    for e in data[ek].values()
                    if e.get("metadata") and "model" in e["metadata"]
                }
                if len(models) > 1:
                    out.append(
                        Violation(
                            self.name,
                            f"users/{uid}/sessions/{sid}",
                            f"models: {models}",
                        )
                    )
        return out

    def normalize(self, data):
        """Set all AI events to the most common model in the session."""
        fixed = 0
        for key in _session_keys(data):
            uid = key.split("/")[1]
            for sid, _ in data[key].items():
                ek = _events_key(uid, sid)
                if ek not in data:
                    continue
                counts: Counter[str] = Counter()
                for e in data[ek].values():
                    md = e.get("metadata")
                    if md and "model" in md:
                        counts[md["model"]] += 1
                if len(counts) > 1:
                    winner = counts.most_common(1)[0][0]
                    for e in data[ek].values():
                        md = e.get("metadata")
                        if md and "model" in md:
                            md["model"] = winner
                    fixed += 1
        return fixed


class MinEventCount(Check):
    """Sessions must have event_count >= 2."""

    name = "min_event_count"

    def violations(self, data):
        out = []
        for key in _session_keys(data):
            uid = key.split("/")[1]
            for sid, session in data[key].items():
                if session.get("event_count", 0) < 2:
                    out.append(
                        Violation(
                            self.name,
                            f"users/{uid}/sessions/{sid}",
                            f"event_count={session.get('event_count')}",
                        )
                    )
        return out

    def normalize(self, data):
        """Delete sessions with fewer than 2 events."""
        fixed = 0
        for key in list(_session_keys(data)):
            uid = key.split("/")[1]
            to_delete = [
                sid for sid, s in data[key].items() if s.get("event_count", 0) < 2
            ]
            for sid in to_delete:
                data.pop(_events_key(uid, sid), None)
                del data[key][sid]
                fixed += 1
        return fixed


class CoachInterventionIntegrity(Check):
    """Coach interventions must reference a valid AI event in the same session,
    and the session's counterfactual fields must be consistent with the
    presence of interventions.

    Invariants checked:
      - Every `coach_intervention` event has metadata with category + kind + mode.
      - `metadata.targets_event_id` (if set) points to an event in the same session.
      - Session's `intervention_count` matches the actual count of coach events.
      - `counterfactual_events` is present iff `intervention_count > 0`.
      - `counterfactual_utility` is present iff `counterfactual_events` is set.

    Normalization recomputes session rollups and clears orphan counterfactuals.
    """

    name = "coach_intervention_integrity"

    VALID_CATEGORIES = {"factuality", "efficiency", "sources", "other"}
    VALID_MODES = {"rewrite", "amend", "inject", "block"}

    def _coach_events(self, data, uid, sid):
        ek = _events_key(uid, sid)
        if ek not in data:
            return {}
        return {
            eid: e
            for eid, e in data[ek].items()
            if e.get("event_type") == "coach_intervention"
        }

    def violations(self, data):
        out = []
        for key in _session_keys(data):
            uid = key.split("/")[1]
            for sid, session in data[key].items():
                coach_events = self._coach_events(data, uid, sid)
                ek = _events_key(uid, sid)
                event_ids = set(data.get(ek, {}).keys())

                for eid, ev in coach_events.items():
                    md = ev.get("metadata") or {}
                    for field in ("category", "kind", "mode"):
                        if not md.get(field):
                            out.append(
                                Violation(
                                    self.name,
                                    f"{ek}/{eid}",
                                    f"missing metadata.{field}",
                                )
                            )
                    if (c := md.get("category")) and c not in self.VALID_CATEGORIES:
                        out.append(
                            Violation(self.name, f"{ek}/{eid}", f"invalid category={c}")
                        )
                    if (m := md.get("mode")) and m not in self.VALID_MODES:
                        out.append(
                            Violation(self.name, f"{ek}/{eid}", f"invalid mode={m}")
                        )
                    tgt = md.get("targets_event_id")
                    if tgt and tgt not in event_ids:
                        out.append(
                            Violation(
                                self.name,
                                f"{ek}/{eid}",
                                f"targets_event_id={tgt} not in session",
                            )
                        )

                actual_count = len(coach_events)
                declared = session.get("intervention_count", 0) or 0
                if actual_count != declared:
                    out.append(
                        Violation(
                            self.name,
                            f"users/{uid}/sessions/{sid}",
                            f"intervention_count={declared}, actual={actual_count}",
                        )
                    )

                has_cf = bool(session.get("counterfactual_events"))
                has_cf_util = session.get("counterfactual_utility") is not None
                if actual_count > 0 and not has_cf:
                    out.append(
                        Violation(
                            self.name,
                            f"users/{uid}/sessions/{sid}",
                            "coached but no counterfactual_events",
                        )
                    )
                if actual_count == 0 and has_cf:
                    out.append(
                        Violation(
                            self.name,
                            f"users/{uid}/sessions/{sid}",
                            "counterfactual_events without interventions",
                        )
                    )
                if has_cf and not has_cf_util:
                    out.append(
                        Violation(
                            self.name,
                            f"users/{uid}/sessions/{sid}",
                            "counterfactual_events without counterfactual_utility",
                        )
                    )
                if has_cf_util and not has_cf:
                    out.append(
                        Violation(
                            self.name,
                            f"users/{uid}/sessions/{sid}",
                            "counterfactual_utility without counterfactual_events",
                        )
                    )
        return out

    def normalize(self, data):
        fixed = 0
        for key in _session_keys(data):
            uid = key.split("/")[1]
            for sid, session in data[key].items():
                coach_events = self._coach_events(data, uid, sid)
                actual_count = len(coach_events)

                categories = sorted(
                    {
                        (e.get("metadata") or {}).get("category")
                        for e in coach_events.values()
                    }
                    - {None}
                )

                # Rebuild rollups from the source of truth (events).
                if session.get("intervention_count", 0) != actual_count:
                    session["intervention_count"] = actual_count
                    fixed += 1
                if categories:
                    if session.get("intervention_categories") != categories:
                        session["intervention_categories"] = categories
                        fixed += 1
                elif session.get("intervention_categories"):
                    session["intervention_categories"] = None
                    fixed += 1

                # Clear counterfactual on uncoached sessions.
                if actual_count == 0:
                    if session.get("counterfactual_events"):
                        session["counterfactual_events"] = None
                        fixed += 1
                    if session.get("counterfactual_utility") is not None:
                        session["counterfactual_utility"] = None
                        fixed += 1
        return fixed


class EventModelMatchesProvider(Check):
    """AI event model must belong to the session's provider."""

    name = "event_model_matches_provider"

    def violations(self, data):
        out = []
        for key in _session_keys(data):
            uid = key.split("/")[1]
            for sid, session in data[key].items():
                prov = session.get("provider")
                if not prov or prov not in PROVIDER_MODELS:
                    continue
                valid = set(PROVIDER_MODELS[prov])
                ek = _events_key(uid, sid)
                if ek not in data:
                    continue
                for eid, event in data[ek].items():
                    md = event.get("metadata")
                    if md and "model" in md and md["model"] not in valid:
                        out.append(
                            Violation(
                                self.name,
                                f"{ek}/{eid}",
                                f"model={md['model']}, provider={prov}",
                            )
                        )
        return out

    def normalize(self, data):
        """Reassign mismatched models to a valid one for the provider."""
        fixed = 0
        for key in _session_keys(data):
            uid = key.split("/")[1]
            for sid, session in data[key].items():
                prov = session.get("provider")
                if not prov or prov not in PROVIDER_MODELS:
                    continue
                valid = set(PROVIDER_MODELS[prov])
                ek = _events_key(uid, sid)
                if ek not in data:
                    continue
                replacement = random.choice(PROVIDER_MODELS[prov])
                session_fixed = False
                for event in data[ek].values():
                    md = event.get("metadata")
                    if md and "model" in md and md["model"] not in valid:
                        md["model"] = replacement
                        session_fixed = True
                if session_fixed:
                    fixed += 1
        return fixed


class PrivacyModeIntegrity(Check):
    """Snapshot data must honour each org's privacy_mode flag.

    For every root org (depth=0) with privacy_mode=True, no insight with a
    personal kind (cross_department_interest / above_paygrade / below_paygrade
    / negative_roi_pattern) may exist for a user belonging to that subtree.
    Snapshots that violate this would expose individuals at runtime if the
    privacy guard ever stopped filtering — so the data layer enforces it too.
    """

    name = "privacy_mode_integrity"

    # Mirror seerai.privacy.PERSONAL_INSIGHT_KINDS — duplicated here to keep
    # plausibility.py importable without FastAPI deps.
    _PERSONAL = frozenset({
        "cross_department_interest",
        "above_paygrade",
        "below_paygrade",
        "negative_roi_pattern",
    })

    def _privacy_subtree_orgs(self, data: dict) -> set[str]:
        orgs = data.get("orgs", {})
        privacy_roots = {
            oid for oid, o in orgs.items()
            if o.get("depth") == 0 and o.get("privacy_mode")
        }
        if not privacy_roots:
            return set()
        return {
            oid for oid, o in orgs.items()
            if any(r in (o.get("path") or []) for r in privacy_roots)
        }

    def violations(self, data: dict) -> list[Violation]:
        privacy_orgs = self._privacy_subtree_orgs(data)
        if not privacy_orgs:
            return []
        out: list[Violation] = []
        for iid, insight in data.get("insights", {}).items():
            if insight.get("kind") not in self._PERSONAL:
                continue
            if insight.get("org_id") in privacy_orgs:
                out.append(Violation(
                    self.name,
                    f"insights/{iid}",
                    f"personal-kind insight ({insight['kind']}) for "
                    f"org={insight.get('org_id')} in privacy-mode subtree",
                ))
        return out

    def normalize(self, data: dict) -> int:
        """Drop offending personal-kind insights from privacy-mode subtrees."""
        privacy_orgs = self._privacy_subtree_orgs(data)
        if not privacy_orgs:
            return 0
        insights = data.get("insights", {})
        to_drop = [
            iid for iid, insight in insights.items()
            if insight.get("kind") in self._PERSONAL
            and insight.get("org_id") in privacy_orgs
        ]
        for iid in to_drop:
            del insights[iid]
        return len(to_drop)


# Ordered: SubscriptionCoverage must precede ProviderMatch so newly-added
# subscriptions are visible when checking provider consistency.
ALL_CHECKS: list[Check] = [
    SubscriptionCoverage(),
    ProviderMatch(),
    SessionEndsOnAI(),
    SessionStartsWithUser(),
    SingleModelPerSession(),
    MinEventCount(),
    EventModelMatchesProvider(),
    CoachInterventionIntegrity(),
    PrivacyModeIntegrity(),
]


# ── runner ───────────────────────────────────────────────────────────────


def load_snapshot(path: Path = SNAPSHOT_PATH) -> dict:
    with open(path) as f:
        return json.load(f)


def save_snapshot(data: dict, path: Path = SNAPSHOT_PATH) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def check_all(data: dict) -> list[Violation]:
    """Run all checks, return violations."""
    out: list[Violation] = []
    for c in ALL_CHECKS:
        out.extend(c.violations(data))
    return out


def normalize_all(data: dict) -> dict[str, tuple[int, int]]:
    """Run checks with normalization. Returns {name: (found, fixed)}."""
    results: dict[str, tuple[int, int]] = {}
    for c in ALL_CHECKS:
        found = len(c.violations(data))
        fixed = c.normalize(data) if found else 0
        results[c.name] = (found, fixed)
    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Check/fix data plausibility")
    parser.add_argument(
        "--fix", action="store_true", help="Normalize violations in-place"
    )
    args = parser.parse_args()

    data = load_snapshot()

    if args.fix:
        results = normalize_all(data)
        for name, (found, fixed) in results.items():
            if found:
                print(f"  {name}: {found} found, {fixed} fixed")
            else:
                print(f"  {name}: clean")
        remaining = check_all(data)
        if remaining:
            print(f"\n{len(remaining)} violations remain:")
            for v in remaining:
                print(f"  {v}")
        else:
            print("\nAll clean after normalization.")
        save_snapshot(data)
    else:
        violations = check_all(data)
        for v in violations:
            print(v)
        n = len(violations)
        suffix = ". Run with --fix to normalize." if n else "."
        print(f"\n{n} violation{'s' if n != 1 else ''} found{suffix}")


if __name__ == "__main__":
    main()
