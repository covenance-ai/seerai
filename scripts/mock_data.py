"""Populate Firestore with a realistic org tree, users, sessions, and events.

Usage:
    uv run python scripts/mock_data.py [--clear]

The --clear flag deletes all existing data before populating.
"""

import argparse
import random
import uuid
from datetime import UTC, datetime, timedelta

from google.cloud.firestore import Client

DB = Client(project="covenance-469421", database="seerai")

# --- Org tree definitions ---

ORG_TREE = {
    "acme": {
        "name": "Acme Corp",
        "children": {
            "acme-eng": {
                "name": "Engineering",
                "children": {
                    "acme-eng-backend": {"name": "Backend"},
                    "acme-eng-frontend": {"name": "Frontend"},
                    "acme-eng-infra": {"name": "Infrastructure"},
                },
            },
            "acme-product": {
                "name": "Product",
                "children": {
                    "acme-product-design": {"name": "Design"},
                    "acme-product-research": {"name": "Research"},
                },
            },
            "acme-sales": {
                "name": "Sales",
                # No sub-teams — users report directly here
            },
        },
    },
    "initech": {
        "name": "Initech",
        "children": {
            "initech-rd": {
                "name": "R&D",
                "children": {
                    "initech-rd-ml": {"name": "Machine Learning"},
                },
            },
            "initech-ops": {
                "name": "Operations",
                # No sub-teams
            },
        },
    },
}

# Users assigned to leaf and mid-level nodes
USERS = {
    "acme-eng-backend": [
        "alice.johnson",
        "bob.martinez",
        "carol.chen",
        "dave.wilson",
        "eve.kim",
    ],
    "acme-eng-frontend": ["frank.lopez", "grace.patel", "henry.nguyen"],
    "acme-eng-infra": ["iris.brown", "jack.taylor"],
    "acme-product-design": ["kate.davis", "liam.moore", "mia.anderson"],
    "acme-product-research": ["noah.thomas", "olivia.jackson"],
    "acme-sales": ["peter.white", "quinn.harris", "rachel.martin", "sam.garcia"],
    "initech-rd-ml": ["tina.clark", "uma.lewis", "victor.hall"],
    "initech-ops": ["wendy.young", "xander.king"],
}

# Users with exec role (can see org dashboard)
EXECS = {
    "alice.johnson",  # Acme backend lead
    "kate.davis",  # Acme product design lead
    "peter.white",  # Acme sales lead
    "tina.clark",  # Initech ML lead
}

# Hourly rate ranges by org (min, max) — reflects typical paygrade bands
HOURLY_RATES = {
    "acme-eng-backend": (60, 120),
    "acme-eng-frontend": (55, 110),
    "acme-eng-infra": (65, 130),
    "acme-product-design": (50, 100),
    "acme-product-research": (55, 105),
    "acme-sales": (35, 75),
    "initech-rd-ml": (70, 140),
    "initech-ops": (40, 80),
}

# Session utility distribution weights: (non_work, trivial, useful)
UTILITY_WEIGHTS = [0.15, 0.40, 0.45]
UTILITY_CLASSES = ["non_work", "trivial", "useful"]

# Realistic conversation snippets
USER_MESSAGES = [
    "Can you explain how GDPR consent requirements work?",
    "What are the key differences between DPIA and PIA?",
    "Help me draft a data processing agreement for our vendor.",
    "Review this privacy policy section for compliance issues.",
    "What data retention periods does GDPR recommend?",
    "Explain the right to erasure and its exceptions.",
    "How should we handle a data breach notification?",
    "What are the requirements for cross-border data transfers?",
    "Can you summarize Article 35 of GDPR for me?",
    "Help me create a record of processing activities.",
    "What security measures does GDPR Article 32 require?",
    "Explain the legal bases for processing personal data.",
    "How do we implement privacy by design in our system?",
    "What are the penalties for GDPR non-compliance?",
    "Review our cookie consent implementation.",
    "Help me assess if we need a Data Protection Officer.",
    "What counts as personal data under GDPR?",
    "Explain the difference between a controller and processor.",
    "How should we handle subject access requests?",
    "Draft an email template for data breach notification.",
]

AI_RESPONSES = [
    "Under GDPR, consent must be freely given, specific, informed, and unambiguous. The data subject must take a clear affirmative action. Pre-ticked boxes are not valid consent.",
    "A DPIA (Data Protection Impact Assessment) is specifically required under GDPR Article 35 when processing is likely to result in high risk. A PIA is a broader, more general privacy assessment.",
    "Here's a draft data processing agreement covering the key clauses required under Article 28: purpose limitation, security measures, sub-processor management, audit rights, and data deletion obligations.",
    "I've identified three compliance issues in this section: (1) the lawful basis for processing isn't clearly stated, (2) data retention periods are missing, and (3) the right to lodge a complaint isn't mentioned.",
    "GDPR doesn't prescribe specific retention periods. You should retain data only as long as necessary for the purpose. Document your retention policy with clear justifications for each data category.",
    "Article 17 grants the right to erasure ('right to be forgotten'). Exceptions include: compliance with legal obligations, public interest, archiving purposes, and establishment/exercise of legal claims.",
    "Under Articles 33-34, you must notify the supervisory authority within 72 hours of becoming aware of a breach. If the breach poses high risk to individuals, you must also notify them directly.",
    "Post-Schrems II, transfers outside the EEA require: adequacy decisions, Standard Contractual Clauses with supplementary measures, or Binding Corporate Rules. Transfer Impact Assessments are recommended.",
    "Article 35 requires a DPIA when processing involves: systematic profiling with significant effects, large-scale processing of special categories, or large-scale systematic monitoring of public areas.",
    "A Record of Processing Activities (ROPA) under Article 30 must include: purposes, data categories, recipients, transfers, retention periods, and technical/organizational security measures.",
]

PROVIDERS = ["anthropic", "openai", "google", "mistral"]
PLATFORMS = ["chrome", "firefox", "vscode", "cli", "slack", "safari"]

# Subscription plans — (provider, plan_name, monthly_cost_cents)
SUBSCRIPTION_PLANS = [
    ("anthropic", "Claude Pro", 2000),
    ("openai", "ChatGPT Plus", 2000),
    ("google", "Gemini Advanced", 2000),
]

ERROR_MESSAGES = [
    "Rate limit exceeded. Please try again in 30 seconds.",
    "Context window exceeded. Consider breaking your request into smaller parts.",
    "Service temporarily unavailable. The model is being updated.",
    "Invalid input: message exceeds maximum token length.",
]


def flatten_tree(
    tree: dict,
    parent_id: str | None = None,
    path: list[str] | None = None,
    depth: int = 0,
) -> list[dict]:
    """Flatten the nested org tree definition into a list of OrgNode dicts."""
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
            nodes.extend(flatten_tree(info["children"], org_id, node_path, depth + 1))
    return nodes


def clear_collection(collection_path: str):
    """Delete all documents in a collection (non-recursive)."""
    docs = DB.collection(collection_path).stream()
    for doc in docs:
        doc.reference.delete()


def clear_all():
    """Delete all orgs, users (with subcollections), and subscriptions."""
    print("Clearing subscriptions...")
    clear_collection("subscriptions")

    print("Clearing orgs...")
    clear_collection("orgs")

    print("Clearing users and their sessions/events...")
    for user_doc in DB.collection("users").stream():
        uid = user_doc.id
        for sess_doc in (
            DB.collection("users").document(uid).collection("sessions").stream()
        ):
            sid = sess_doc.id
            for evt_doc in (
                DB.collection("users")
                .document(uid)
                .collection("sessions")
                .document(sid)
                .collection("events")
                .stream()
            ):
                evt_doc.reference.delete()
            sess_doc.reference.delete()
        user_doc.reference.delete()
    print("Cleared.")


def create_orgs():
    """Write all org nodes to Firestore."""
    nodes = flatten_tree(ORG_TREE)
    batch = DB.batch()
    for n in nodes:
        batch.set(DB.collection("orgs").document(n["org_id"]), n)
    batch.commit()
    print(f"Created {len(nodes)} org nodes.")
    return nodes


def create_users_and_data():
    """Create users with sessions and events."""
    now = datetime.now(UTC)
    total_users = 0
    total_sessions = 0
    total_events = 0

    for org_id, user_list in USERS.items():
        for user_id in user_list:
            total_users += 1
            num_sessions = random.randint(2, 8)

            # Spread sessions over last 30 days
            session_starts = sorted(
                [
                    now - timedelta(days=random.uniform(0, 30))
                    for _ in range(num_sessions)
                ]
            )

            last_active = session_starts[-1]

            # Write user document
            role = "exec" if user_id in EXECS else "user"
            rate_min, rate_max = HOURLY_RATES[org_id]
            hourly_rate = round(random.uniform(rate_min, rate_max), 2)
            DB.collection("users").document(user_id).set(
                {
                    "user_id": user_id,
                    "org_id": org_id,
                    "role": role,
                    "last_active": last_active,
                    "hourly_rate": hourly_rate,
                }
            )

            for session_start in session_starts:
                total_sessions += 1
                session_id = str(uuid.uuid4())
                provider = random.choice(PROVIDERS)
                platform = random.choice(PLATFORMS)
                num_events = random.randrange(
                    4, 21, 2
                )  # always even → ends on ai_message
                event_count = 0
                error_count = 0

                # Events spread over 5-60 minutes
                session_duration = timedelta(minutes=random.uniform(5, 60))
                event_times = sorted(
                    [
                        session_start + session_duration * (i / num_events)
                        for i in range(num_events)
                    ]
                )

                batch = DB.batch()
                last_event_type = None

                for j, event_time in enumerate(event_times):
                    total_events += 1
                    event_count += 1
                    event_id = str(uuid.uuid4())

                    # Alternate user/ai, with ~5% errors on AI turns (never first/last)
                    is_user_turn = j % 2 == 0
                    if is_user_turn:
                        event_type = "user_message"
                        content = random.choice(USER_MESSAGES)
                    elif 0 < j < num_events - 1 and random.random() < 0.10:
                        event_type = "error"
                        content = random.choice(ERROR_MESSAGES)
                        error_count += 1
                    else:
                        event_type = "ai_message"
                        content = random.choice(AI_RESPONSES)

                    last_event_type = event_type

                    metadata = None
                    if event_type == "ai_message":
                        metadata = {
                            "model": random.choice(
                                ["claude-sonnet-4", "gpt-4o", "gemini-2.0-flash"]
                            ),
                            "tokens": random.randint(50, 800),
                            "latency_ms": random.randint(200, 3000),
                        }

                    event_ref = (
                        DB.collection("users")
                        .document(user_id)
                        .collection("sessions")
                        .document(session_id)
                        .collection("events")
                        .document(event_id)
                    )
                    batch.set(
                        event_ref,
                        {
                            "event_id": event_id,
                            "event_type": event_type,
                            "content": content,
                            "metadata": metadata,
                            "timestamp": event_time,
                        },
                    )

                batch.commit()

                # Write session summary
                utility = random.choices(UTILITY_CLASSES, UTILITY_WEIGHTS)[0]
                session_data = {
                    "session_id": session_id,
                    "user_id": user_id,
                    "last_event_at": event_times[-1],
                    "last_event_type": last_event_type,
                    "event_count": event_count,
                    "provider": provider,
                    "platform": platform,
                    "utility": utility,
                }
                if error_count > 0:
                    session_data["error_count"] = error_count

                DB.collection("users").document(user_id).collection(
                    "sessions"
                ).document(session_id).set(session_data)

            # Update user last_active to latest session
            DB.collection("users").document(user_id).update(
                {"last_active": last_active}
            )

    print(
        f"Created {total_users} users, {total_sessions} sessions, {total_events} events."
    )


def create_subscriptions():
    """Assign 1-2 AI subscriptions per user, with some users having none."""
    now = datetime.now(UTC)
    total = 0
    batch = DB.batch()

    all_users = []
    for user_list in USERS.values():
        all_users.extend(user_list)

    for user_id in all_users:
        # ~80% of users get at least one subscription
        if random.random() < 0.2:
            continue

        # Pick 1-2 random plans
        num_plans = random.choices([1, 2], weights=[0.6, 0.4])[0]
        plans = random.sample(SUBSCRIPTION_PLANS, num_plans)

        for provider, plan_name, cost_cents in plans:
            sub_id = str(uuid.uuid4())
            started_at = now - timedelta(days=random.randint(30, 180))
            batch.set(
                DB.collection("subscriptions").document(sub_id),
                {
                    "subscription_id": sub_id,
                    "user_id": user_id,
                    "provider": provider,
                    "plan": plan_name,
                    "monthly_cost_cents": cost_cents,
                    "currency": "USD",
                    "started_at": started_at,
                    "ended_at": None,
                },
            )
            total += 1

    batch.commit()
    print(f"Created {total} subscriptions.")


def main():
    parser = argparse.ArgumentParser(description="Populate seerai with mock data")
    parser.add_argument(
        "--clear", action="store_true", help="Clear all data before populating"
    )
    args = parser.parse_args()

    if args.clear:
        clear_all()

    create_orgs()
    create_users_and_data()
    create_subscriptions()
    print("Done.")


if __name__ == "__main__":
    main()
