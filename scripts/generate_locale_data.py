"""Generate a localized demo snapshot directly to ``data/snapshot.<lang>.json``.

The structure mirrors ``scripts/mock_data.py`` but:
  - Writes through ``seerai.local_client.LocalStore`` instead of Firestore.
  - Pulls company names, users, hourly rates, and industry-specific message
    templates from ``seerai.locale_data.LocaleConfig``.
  - Embeds a small set of archetype sessions with full transcripts so the
    session-detail page renders native content even on stub sessions.

Usage:
    uv run python scripts/generate_locale_data.py de
    uv run python scripts/generate_locale_data.py it --clear
    uv run python scripts/generate_locale_data.py de it en

``--clear`` deletes the target snapshot file first (the default is additive,
which rarely makes sense — prefer ``--clear``).
"""

from __future__ import annotations

import argparse
import random
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from seerai.local_client import LocalStore
from seerai.locale_data import LOCALES, LocaleConfig

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

# Keep in sync with mock_data.py / plausibility.py — these are shared across
# locales since providers/platforms/models are global.
PROVIDERS = ["anthropic", "openai", "google", "mistral"]
PLATFORMS = ["chrome", "firefox", "vscode", "cli", "slack", "safari"]
PROVIDER_MODELS = {
    "anthropic": ["claude-sonnet-4", "claude-haiku-4"],
    "openai": ["gpt-4o", "o3-mini"],
    "google": ["gemini-2.0-flash", "gemini-2.5-pro"],
    "mistral": ["mistral-large", "mistral-small"],
}
SUBSCRIPTION_PLANS = [
    ("anthropic", "Claude Pro", 2000),
    ("openai", "ChatGPT Plus", 2000),
    ("google", "Gemini Advanced", 2000),
    ("mistral", "Le Chat Pro", 1500),
]

UTILITY_WEIGHTS = [0.15, 0.40, 0.45]
UTILITY_CLASSES = ["non_work", "trivial", "useful"]


def snapshot_path(lang: str) -> Path:
    """Snapshot file path for a locale.

    English keeps the legacy ``snapshot.json`` filename so existing tooling
    (CLI, tests, and external references) keeps working; other locales use
    the ``snapshot.<lang>.json`` form.
    """
    if lang == "en":
        return DATA_DIR / "snapshot.json"
    return DATA_DIR / f"snapshot.{lang}.json"


# ── helpers mirroring mock_data.py, parameterized on LocaleConfig ─────────


def _flatten_tree(tree, parent_id=None, path=None, depth=0):
    """Same semantics as mock_data.flatten_tree but locale-agnostic."""
    nodes = []
    for org_id, info in tree.items():
        node_path = (path or []) + [org_id]
        nodes.append(
            {
                "org_id": org_id,
                "name": info["name"],
                "parent_id": parent_id,
                "path": node_path,
                "depth": depth,
            }
        )
        if "children" in info:
            nodes.extend(_flatten_tree(info["children"], org_id, node_path, depth + 1))
    return nodes


def _assign_subscriptions(locale: LocaleConfig) -> dict[str, list[tuple[str, str, int]]]:
    """Give each user one or two provider subscriptions (currency from locale)."""
    assignments: dict[str, list[tuple[str, str, int]]] = {}
    for user_list in locale.users.values():
        for user_id in user_list:
            num_plans = random.choices([1, 2], weights=[0.6, 0.4])[0]
            plans = random.sample(SUBSCRIPTION_PLANS, num_plans)
            assignments[user_id] = plans
    return assignments


def _write_orgs(db: LocalStore, locale: LocaleConfig) -> int:
    nodes = _flatten_tree(locale.org_tree)
    batch = db.batch()
    for n in nodes:
        batch.set(db.collection("orgs").document(n["org_id"]), n)
    batch.commit()
    return len(nodes)


def _build_event(
    idx: int,
    total: int,
    event_time: datetime,
    locale: LocaleConfig,
    session_model: str,
) -> dict:
    """Build one mock event — pure data, no DB writes."""
    event_id = str(uuid.uuid4())
    is_user_turn = idx % 2 == 0
    if is_user_turn:
        event_type = "user_message"
        content = random.choice(locale.user_messages)
        metadata = None
    elif 0 < idx < total - 1 and random.random() < 0.10:
        event_type = "error"
        content = random.choice(locale.error_messages)
        metadata = None
    else:
        event_type = "ai_message"
        content = random.choice(locale.ai_responses)
        metadata = {
            "model": session_model,
            "tokens": random.randint(50, 800),
            "latency_ms": random.randint(200, 3000),
        }
    return {
        "event_id": event_id,
        "event_type": event_type,
        "content": content,
        "metadata": metadata,
        "timestamp": event_time,
    }


def _write_users_and_sessions(db: LocalStore, locale: LocaleConfig, subs):
    """Create users + one mixed "hero" session each (every 3rd has real events)."""
    now = datetime.now(UTC)
    log: dict[str, list] = {}

    total_sessions = total_events = 0

    for org_id, user_list in locale.users.items():
        for user_id in user_list:
            rate_min, rate_max = locale.hourly_rates[org_id]
            hourly_rate = round(random.uniform(rate_min, rate_max), 2)
            role = "exec" if user_id in locale.execs else "user"

            num_sessions = random.randint(2, 8)
            session_starts = sorted(
                now - timedelta(days=random.uniform(0, 30))
                for _ in range(num_sessions)
            )
            last_active = session_starts[-1]

            db.collection("users").document(user_id).set(
                {
                    "user_id": user_id,
                    "org_id": org_id,
                    "role": role,
                    "last_active": last_active,
                    "hourly_rate": hourly_rate,
                }
            )

            user_providers = [p for p, _, _ in subs[user_id]]

            for idx, session_start in enumerate(session_starts):
                total_sessions += 1
                session_id = str(uuid.uuid4())
                provider = random.choice(user_providers)
                model = random.choice(PROVIDER_MODELS[provider])
                platform = random.choice(PLATFORMS)

                # ~30% of sessions carry real events — the rest are stubs
                # (cheap volume) and will fall back to archetype content on
                # the detail page.
                with_events = idx % 3 == 0

                event_count = random.randrange(4, 21, 2)  # even → ends on AI
                error_count = 0

                session_duration = timedelta(minutes=random.uniform(5, 60))
                event_times = sorted(
                    session_start + session_duration * (i / event_count)
                    for i in range(event_count)
                )

                if with_events:
                    events = [
                        _build_event(i, event_count, t, locale, model)
                        for i, t in enumerate(event_times)
                    ]
                    # Ensure last is not user_message (plausibility rule);
                    # with even counts this already holds, but be defensive.
                    if events[-1]["event_type"] == "user_message":
                        events.pop()
                        event_count -= 1
                    error_count = sum(1 for e in events if e["event_type"] == "error")

                    batch = db.batch()
                    for ev in events:
                        ref = (
                            db.collection("users")
                            .document(user_id)
                            .collection("sessions")
                            .document(session_id)
                            .collection("events")
                            .document(ev["event_id"])
                        )
                        batch.set(ref, ev)
                        total_events += 1
                    batch.commit()
                    last_event_at = events[-1]["timestamp"]
                    last_event_type = events[-1]["event_type"]
                else:
                    last_event_at = event_times[-1]
                    last_event_type = "ai_message"

                utility = random.choices(UTILITY_CLASSES, UTILITY_WEIGHTS)[0]
                session_data = {
                    "session_id": session_id,
                    "user_id": user_id,
                    "last_event_at": last_event_at,
                    "last_event_type": last_event_type,
                    "event_count": event_count,
                    "provider": provider,
                    "platform": platform,
                    "utility": utility,
                }
                if error_count:
                    session_data["error_count"] = error_count

                db.collection("users").document(user_id).collection(
                    "sessions"
                ).document(session_id).set(session_data)

                log.setdefault(user_id, []).append(
                    (session_id, utility, hourly_rate, org_id)
                )

            db.collection("users").document(user_id).update(
                {"last_active": last_active}
            )

    return log, total_sessions, total_events


def _write_archetype_sessions(
    db: LocalStore, locale: LocaleConfig, subs: dict
) -> int:
    """Write locale.archetypes as full-event sessions on the first users.

    Each archetype uses a stable, predictable user so the dynamic archetype
    matcher in ``seerai.archetypes`` finds it reliably. Sessions are spread
    across the last 5 days so they appear near the top of the "recent" list.

    If the chosen user isn't subscribed to the archetype's provider, we
    extend their subscription list in-place and write a matching
    subscription — otherwise the plausibility checker would reject the
    session for using an unsubscribed provider.
    """
    if not locale.archetypes:
        return 0

    # Take deterministic users: first user in each org (insertion order).
    all_users = [
        u
        for users in locale.users.values()
        for u in users
    ]
    if not all_users:
        return 0

    now = datetime.now(UTC)
    written = 0
    for i, archetype in enumerate(locale.archetypes):
        user_id = all_users[i % len(all_users)]
        session_id = str(uuid.uuid4())
        provider = archetype.get("provider", random.choice(PROVIDERS))

        # Ensure the archetype user is subscribed to the archetype provider.
        user_providers = {p for p, _, _ in subs.get(user_id, [])}
        if provider not in user_providers:
            plan = next(
                (p for p in SUBSCRIPTION_PLANS if p[0] == provider),
                None,
            )
            if plan:
                subs.setdefault(user_id, []).append(plan)

        model = random.choice(PROVIDER_MODELS[provider])
        platform = random.choice(PLATFORMS)
        utility = archetype.get("utility", "useful")
        turns = archetype.get("turns", [])
        if len(turns) < 2:
            continue

        # Place this archetype between 1 and 5 days ago, spaced out.
        session_start = now - timedelta(days=i + 1, hours=random.uniform(0, 20))
        event_times = [
            session_start + timedelta(minutes=2 * j) for j in range(len(turns))
        ]

        events = []
        for j, ((role, content), ts) in enumerate(zip(turns, event_times)):
            event_type = "ai_message" if role == "ai" else "user_message"
            metadata = None
            if event_type == "ai_message":
                metadata = {
                    "model": model,
                    "tokens": 50 + 20 * len(content.split()),
                    "latency_ms": random.randint(400, 2200),
                }
            events.append(
                {
                    "event_id": str(uuid.uuid4()),
                    "event_type": event_type,
                    "content": content,
                    "metadata": metadata,
                    "timestamp": ts,
                }
            )

        batch = db.batch()
        for ev in events:
            ref = (
                db.collection("users")
                .document(user_id)
                .collection("sessions")
                .document(session_id)
                .collection("events")
                .document(ev["event_id"])
            )
            batch.set(ref, ev)
        batch.commit()

        token_usage: dict[str, int] = {}
        for ev in events:
            md = ev["metadata"]
            if md and ev["event_type"] == "ai_message":
                token_usage[md["model"]] = token_usage.get(md["model"], 0) + md["tokens"]

        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "last_event_at": events[-1]["timestamp"],
            "last_event_type": events[-1]["event_type"],
            "event_count": len(events),
            "provider": provider,
            "platform": platform,
            "utility": utility,
            "token_usage": token_usage or None,
        }
        db.collection("users").document(user_id).collection("sessions").document(
            session_id
        ).set(session_data)
        written += 1

    return written


def _write_stub_sessions(db: LocalStore, locale: LocaleConfig, subs, session_log):
    """Cheap volume — sessions without events.

    Detail pages for these fall back to archetype transcripts.
    """
    now = datetime.now(UTC)
    PROFILES = {"power": (8, 20), "moderate": (3, 8), "light": (0, 3)}
    PROFILE_WEIGHTS = [0.2, 0.5, 0.3]

    total = 0
    batch = db.batch()
    batch_size = 0
    latest_per_user: dict[str, datetime] = {}

    for user_list in locale.users.values():
        for user_id in user_list:
            profile = random.choices(list(PROFILES), PROFILE_WEIGHTS)[0]
            min_daily, max_daily = PROFILES[profile]
            user_providers = [p for p, _, _ in subs[user_id]]
            user_platforms = random.sample(PLATFORMS, k=random.randint(1, 2))

            for day in range(30):
                day_start = now - timedelta(days=day + 1)
                num_sessions = random.randint(min_daily, max_daily)
                for _ in range(num_sessions):
                    session_id = str(uuid.uuid4())
                    session_time = day_start + timedelta(
                        hours=random.gauss(14, 3), minutes=random.uniform(0, 60)
                    )
                    duration = timedelta(minutes=random.uniform(2, 45))
                    last_event_at = session_time + duration

                    event_count = max(2, int(random.gauss(10, 6)))
                    event_count += event_count % 2  # round up to even

                    error_count = 0
                    if random.random() < 0.12:
                        error_count = random.randint(1, max(1, event_count // 6))

                    ref = (
                        db.collection("users")
                        .document(user_id)
                        .collection("sessions")
                        .document(session_id)
                    )
                    utility = random.choices(UTILITY_CLASSES, UTILITY_WEIGHTS)[0]
                    stub = {
                        "session_id": session_id,
                        "user_id": user_id,
                        "last_event_at": last_event_at,
                        "last_event_type": "ai_message",
                        "event_count": event_count,
                        "error_count": error_count,
                        "provider": random.choice(user_providers),
                        "platform": random.choice(user_platforms),
                        "utility": utility,
                    }
                    batch.set(ref, stub)
                    batch_size += 1
                    total += 1
                    session_log.setdefault(user_id, []).append(
                        (session_id, utility, 0.0, "")
                    )
                    latest_per_user[user_id] = max(
                        latest_per_user.get(user_id, datetime.min.replace(tzinfo=UTC)),
                        last_event_at,
                    )
                    if batch_size >= 400:
                        batch.commit()
                        batch = db.batch()
                        batch_size = 0

    for user_id, latest in latest_per_user.items():
        batch.set(
            db.collection("users").document(user_id),
            {"last_active": latest},
            merge=True,
        )
        batch_size += 1
    if batch_size:
        batch.commit()
    return total


def _write_subscriptions(db: LocalStore, subs, currency: str) -> int:
    now = datetime.now(UTC)
    total = 0
    batch = db.batch()
    for user_id, plans in subs.items():
        for provider, plan_name, cost_cents in plans:
            sub_id = str(uuid.uuid4())
            started_at = now - timedelta(days=random.randint(30, 180))
            batch.set(
                db.collection("subscriptions").document(sub_id),
                {
                    "subscription_id": sub_id,
                    "user_id": user_id,
                    "provider": provider,
                    "plan": plan_name,
                    "monthly_cost_cents": cost_cents,
                    "currency": currency,
                    "started_at": started_at,
                    "ended_at": None,
                },
            )
            total += 1
    batch.commit()
    return total


def _write_insights(db: LocalStore, locale: LocaleConfig, session_log) -> int:
    """Cross-department + paygrade insights. Narrative text comes from the locale."""
    now = datetime.now(UTC)

    user_stats: dict[str, dict] = {}
    for user_id, entries in session_log.items():
        real = [(sid, u, r, o) for sid, u, r, o in entries if r > 0]
        if not real:
            continue
        rate = real[0][2]
        org_id = real[0][3]
        all_sessions = [(sid, u) for sid, u, _, _ in entries]
        useful = sum(1 for _, u in all_sessions if u == "useful")
        trivial = sum(1 for _, u in all_sessions if u == "trivial")
        non_work = sum(1 for _, u in all_sessions if u == "non_work")
        total = len(all_sessions)
        user_stats[user_id] = {
            "rate": rate,
            "org_id": org_id,
            "total": total,
            "useful_pct": round(100 * useful / total) if total else 0,
            "nonwork_pct": round(100 * non_work / total) if total else 0,
            "trivial_pct": round(100 * trivial / total) if total else 0,
            "session_ids": [sid for sid, _ in all_sessions],
        }

    currency_symbol = "€" if locale.currency == "EUR" else "$"

    batch = db.batch()
    written = 0

    # Localized copy snippets. English uses the existing phrasing; other
    # locales ship their own templates alongside the locale content.
    copy = {
        "en": {
            "cross_title": "{name} exploring {dept} topics",
            "cross_desc": (
                "Analysis of {uid}'s recent sessions reveals sustained engagement "
                "with {dept}-related queries. Over the past 2 weeks, multiple "
                "sessions focused on {topics}. This pattern suggests genuine "
                "interest or an emerging cross-functional need."
            ),
            "above_title": "{name} delivering above-level output",
            "above_desc": (
                "{uid}'s session analysis shows {pct}% of sessions classified "
                "as highly useful, with complex multi-turn problem-solving "
                "patterns typical of higher pay bands. Current rate "
                "({cur}{rate:.0f}/hr) is below the team median, suggesting "
                "possible undercompensation."
            ),
            "below_title": "{name} underutilizing AI relative to role",
            "below_desc": (
                "{uid}'s usage shows {nwp}% non-work and {trp}% trivial "
                "sessions. At {cur}{rate:.0f}/hr, this represents a gap "
                "between expected and actual AI-driven productivity."
            ),
        },
        "de": {
            "cross_title": "{name} beschäftigt sich mit {dept}-Themen",
            "cross_desc": (
                "Die Analyse der jüngsten Sessions von {uid} zeigt anhaltendes "
                "Interesse an Themen des Bereichs {dept}. In den letzten 2 "
                "Wochen konzentrierten sich mehrere Sessions auf {topics}. "
                "Dieses Muster deutet auf echtes Interesse oder einen neu "
                "entstehenden abteilungsübergreifenden Bedarf hin."
            ),
            "above_title": "{name} liefert Leistung über der Gehaltsstufe",
            "above_desc": (
                "{uid}s Sessionanalyse zeigt {pct}% hochwertige Nutzungen mit "
                "komplexer Mehrfachinteraktion, typisch für höhere "
                "Gehaltsbänder. Der aktuelle Stundensatz ({cur}{rate:.0f}/h) "
                "liegt unter dem Teammedian — mögliche Unterbezahlung."
            ),
            "below_title": "{name} nutzt KI unter dem Rollenpotenzial",
            "below_desc": (
                "{uid}s Nutzungsmuster zeigt {nwp}% Nicht-Arbeits- und {trp}% "
                "triviale Sessions. Bei {cur}{rate:.0f}/h klafft hier eine "
                "Lücke zwischen erwarteter und tatsächlicher KI-gestützter "
                "Produktivität."
            ),
        },
        "it": {
            "cross_title": "{name} esplora temi di {dept}",
            "cross_desc": (
                "L'analisi delle sessioni recenti di {uid} rivela un "
                "interesse costante per argomenti di {dept}. Nelle ultime "
                "2 settimane più sessioni si sono concentrate su {topics}. "
                "Il pattern suggerisce un interesse genuino o un'esigenza "
                "interfunzionale emergente."
            ),
            "above_title": "{name} produce risultati sopra la fascia",
            "above_desc": (
                "L'analisi delle sessioni di {uid} mostra {pct}% di sessioni "
                "ad alto valore con pattern di problem solving tipici di "
                "fasce più alte. Il compenso attuale ({cur}{rate:.0f}/h) è "
                "sotto la mediana del team — possibile sotto-retribuzione."
            ),
            "below_title": "{name} sottoutilizza l'IA rispetto al ruolo",
            "below_desc": (
                "L'uso di {uid} mostra {nwp}% di sessioni non lavorative e "
                "{trp}% triviali. A {cur}{rate:.0f}/h c'è un divario tra "
                "produttività attesa e reale dell'IA."
            ),
        },
    }[locale.lang if locale.lang in ("en", "de", "it") else "en"]

    def _display(uid: str) -> str:
        return locale.display_names.get(uid) or uid.split(".")[0].title()

    # ── Cross-department ───────────────────────────────────────────────
    for cd in locale.cross_dept:
        uid = cd["user_id"]
        if uid not in user_stats:
            continue
        stats = user_stats[uid]
        evidence = random.sample(
            stats["session_ids"], min(3, len(stats["session_ids"]))
        )
        insight_id = str(uuid.uuid4())
        days_ago = random.randint(1, 14)
        batch.set(
            db.collection("insights").document(insight_id),
            {
                "insight_id": insight_id,
                "kind": "cross_department_interest",
                "priority": cd["priority"],
                "created_at": now - timedelta(days=days_ago),
                "title": copy["cross_title"].format(
                    name=_display(uid), dept=cd["target_dept"]
                ),
                "description": copy["cross_desc"].format(
                    uid=_display(uid), dept=cd["target_dept"], topics=cd["topics"]
                ),
                "user_id": uid,
                "org_id": stats["org_id"],
                "target_org_id": cd["target_org_id"],
                "evidence_session_ids": evidence,
            },
        )
        written += 1

    # ── Paygrade (above / below) ───────────────────────────────────────
    by_org: dict[str, list] = {}
    for uid, stats in user_stats.items():
        by_org.setdefault(stats["org_id"], []).append((uid, stats))

    above, below = [], []
    for org_id, members in by_org.items():
        if len(members) < 2:
            continue
        rates = [s["rate"] for _, s in members]
        median = sorted(rates)[len(rates) // 2]
        for uid, stats in members:
            if stats["rate"] < median * 0.85 and stats["useful_pct"] > 55:
                above.append((uid, stats))
            elif (
                stats["rate"] > median * 1.1
                and stats["nonwork_pct"] + stats["trivial_pct"] > 60
            ):
                below.append((uid, stats))

    above.sort(key=lambda x: x[1]["useful_pct"], reverse=True)
    below.sort(key=lambda x: x[1]["nonwork_pct"] + x[1]["trivial_pct"], reverse=True)

    for uid, stats in above[:3]:
        insight_id = str(uuid.uuid4())
        days_ago = random.randint(1, 10)
        evidence = stats["session_ids"][:3]
        batch.set(
            db.collection("insights").document(insight_id),
            {
                "insight_id": insight_id,
                "kind": "above_paygrade",
                "priority": 2,
                "created_at": now - timedelta(days=days_ago),
                "title": copy["above_title"].format(name=_display(uid)),
                "description": copy["above_desc"].format(
                    uid=_display(uid),
                    pct=stats["useful_pct"],
                    cur=currency_symbol,
                    rate=stats["rate"],
                ),
                "user_id": uid,
                "org_id": stats["org_id"],
                "target_org_id": None,
                "evidence_session_ids": evidence,
            },
        )
        written += 1

    for uid, stats in below[:3]:
        insight_id = str(uuid.uuid4())
        days_ago = random.randint(1, 10)
        evidence = stats["session_ids"][:3]
        batch.set(
            db.collection("insights").document(insight_id),
            {
                "insight_id": insight_id,
                "kind": "below_paygrade",
                "priority": 1 if stats["nonwork_pct"] > 40 else 3,
                "created_at": now - timedelta(days=days_ago),
                "title": copy["below_title"].format(name=_display(uid)),
                "description": copy["below_desc"].format(
                    uid=_display(uid),
                    nwp=stats["nonwork_pct"],
                    trp=stats["trivial_pct"],
                    cur=currency_symbol,
                    rate=stats["rate"],
                ),
                "user_id": uid,
                "org_id": stats["org_id"],
                "target_org_id": None,
                "evidence_session_ids": evidence,
            },
        )
        written += 1

    batch.commit()
    return written


# ── entrypoint ────────────────────────────────────────────────────────────


def generate(lang: str, clear: bool, seed: int | None = None) -> dict:
    """Generate a snapshot for one locale. Returns counters."""
    locale = LOCALES.get(lang)
    if not locale:
        raise SystemExit(f"Unknown lang: {lang!r}. Supported: {sorted(LOCALES)}")

    path = snapshot_path(lang)
    if clear and path.exists():
        path.unlink()

    if seed is not None:
        random.seed(seed)

    db = LocalStore(path)
    # Wipe every known top-level collection so regenerate = replace. We
    # don't touch collections we don't own.
    for coll in (
        "orgs",
        "users",
        "subscriptions",
        "insights",
    ):
        db.data.pop(coll, None)
    for key in list(db.data.keys()):
        if key.startswith("users/"):
            db.data.pop(key, None)
    # _meta carries locale hints the frontend can read (industry, currency).
    db.data["_meta"] = {
        "lang": locale.lang,
        "country": locale.country,
        "industry": locale.industry,
        "currency": locale.currency,
        "company_brands": locale.company_brands,
        "display_names": locale.display_names,
    }
    db._dirty = True

    subs = _assign_subscriptions(locale)
    counts = {}
    counts["orgs"] = _write_orgs(db, locale)
    log, total_sessions, total_events = _write_users_and_sessions(db, locale, subs)
    counts["users"] = sum(len(v) for v in locale.users.values())
    counts["hero_sessions"] = total_sessions
    counts["hero_events"] = total_events
    counts["archetypes"] = _write_archetype_sessions(db, locale, subs)
    counts["stub_sessions"] = _write_stub_sessions(db, locale, subs, log)
    # Subscriptions written last so they reflect any extra plans the
    # archetype writer may have added for hero users.
    counts["subscriptions"] = _write_subscriptions(db, subs, locale.currency)
    counts["insights"] = _write_insights(db, locale, log)

    db.save()
    return counts


def main():
    parser = argparse.ArgumentParser(
        description="Generate localized demo snapshots (en, de, it)."
    )
    parser.add_argument(
        "langs",
        nargs="+",
        help=f"One or more language codes. Supported: {sorted(LOCALES)}",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete the target snapshot file before regenerating.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Seed random so re-generations are reproducible.",
    )
    args = parser.parse_args()

    for lang in args.langs:
        print(f"\n→ generating {lang} → {snapshot_path(lang).name}")
        counts = generate(lang, clear=args.clear, seed=args.seed)
        for k, v in counts.items():
            print(f"    {k:>15s}: {v}")
        path = snapshot_path(lang)
        if path.exists():
            print(f"    {'size':>15s}: {path.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
