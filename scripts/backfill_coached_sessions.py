"""Generate coached sessions across the org to populate the /coach dashboard.

Picks a spread of users, categories, and intervention styles; calls the
LLM once per session via `generate_coached_session`, writing each result
to the local snapshot.

Usage:
    export OPENAI_API_KEY=...
    uv run --extra generate python scripts/backfill_coached_sessions.py \\
        --count 30 --model openai:gpt-4o
    uv run python -m seerai.plausibility --fix   # after the backfill
"""

from __future__ import annotations

import argparse
import random
import time
from dataclasses import dataclass

from seerai.entities import CoachCategory
from seerai.generate import DEFAULT_MODEL, generate_coached_session


@dataclass(frozen=True)
class Scenario:
    user_id: str
    category: CoachCategory
    style: str  # "flag" | "correct"
    description: str


# Each scenario seeds the LLM with a realistic situation where the base
# model is prone to making the kind of mistake the coach should catch.
# Variety is biased by department: sales/ops skew toward sources and PII;
# engineering skews toward factuality and efficiency.
SCENARIOS: list[Scenario] = [
    # ─── Factuality (engineering skew) ─────────────────────────────────
    Scenario(
        "carol.chen", "factuality", "correct",
        "Engineer asks for the fastest way to group-by and aggregate in polars. "
        "Base AI invents a `LazyFrame.fast_agg()` chained method that doesn't exist.",
    ),
    Scenario(
        "dave.wilson", "factuality", "correct",
        "Engineer asks about SQLAlchemy async session lifecycle. Base AI "
        "hallucinates a `Session.async_commit()` method (actual is `await session.commit()`).",
    ),
    Scenario(
        "eve.kim", "factuality", "flag",
        "Engineer asks whether Python dict ordering is guaranteed across versions. "
        "Base AI says it's only guaranteed from 3.8 (actual: 3.7); coach flags the error.",
    ),
    Scenario(
        "iris.brown", "factuality", "correct",
        "Platform engineer asks about Kubernetes pod disruption budget behavior. "
        "Base AI invents a `maxUnavailable: auto` value (not a real option).",
    ),
    Scenario(
        "jack.taylor", "factuality", "correct",
        "Infra engineer asks Terraform question. Base AI invents a "
        "`aws_eip.managed` resource argument that doesn't exist.",
    ),
    Scenario(
        "victor.hall", "factuality", "correct",
        "ML researcher asks about torch DataLoader num_workers. Base AI confidently "
        "quotes a non-existent benchmark result.",
    ),
    Scenario(
        "noah.thomas", "factuality", "flag",
        "Product researcher asks for a quick stat about user retention curves. "
        "Base AI cites a made-up study from 2018; coach flags but doesn't rewrite.",
    ),

    # ─── Efficiency (drift / wrong tool) ───────────────────────────────
    Scenario(
        "frank.lopez", "efficiency", "correct",
        "Frontend engineer asks about a tailwind utility classes issue. Base AI "
        "drifts into suggesting a full design system rewrite; coach redirects to the one-line fix.",
    ),
    Scenario(
        "grace.patel", "efficiency", "correct",
        "Frontend engineer asks why a React effect fires twice. Base AI drifts into "
        "refactoring the state shape instead of noting StrictMode's intentional double-invocation.",
    ),
    Scenario(
        "henry.nguyen", "efficiency", "correct",
        "Frontend engineer asks about a flaky Jest test. Base AI proposes moving to "
        "Vitest as the solution; coach redirects to the actual issue (unmocked timer).",
    ),
    Scenario(
        "bob.martinez", "efficiency", "correct",
        "Backend engineer debugging slow Postgres query. Base AI suggests migrating to "
        "Timescale; coach redirects: missing index on the filter column.",
    ),
    Scenario(
        "liam.moore", "efficiency", "correct",
        "Product designer asks for help writing a CSV parser. Base AI produces a 120-line "
        "regex; coach redirects to using the csv module.",
    ),
    Scenario(
        "olivia.jackson", "efficiency", "flag",
        "Researcher asks for help plotting a distribution. Base AI gives a working but "
        "overcomplicated matplotlib approach; coach flags seaborn.histplot as the simpler option.",
    ),
    Scenario(
        "uma.lewis", "efficiency", "correct",
        "ML engineer stuck in a loop retraining a model that keeps diverging. Base AI "
        "proposes a third round of hyperparameter tuning; coach redirects: the data has label leakage.",
    ),

    # ─── Sources (sales / research / legal-adjacent) ───────────────────
    Scenario(
        "rachel.martin", "sources", "correct",
        "Sales rep drafting a DPA clause summary for a prospect. Base AI invents "
        "GDPR 'Article 46(5)' (real article exists but subsection is wrong); coach rewrites with the right cite.",
    ),
    Scenario(
        "sam.garcia", "sources", "correct",
        "Sales rep writing a customer-facing benchmark claim. Base AI cites a made-up "
        "Gartner report; coach replaces with the actual Forrester TEI study link.",
    ),
    Scenario(
        "quinn.harris", "sources", "correct",
        "Sales rep writes up an industry stat from memory. Base AI echoes a false 'average data breach cost' figure; "
        "coach corrects with the current IBM Cost of a Data Breach report number.",
    ),
    Scenario(
        "peter.white", "sources", "flag",
        "Sales exec writing a blog post. Base AI weaves in an unsourced quote attributed to a "
        "well-known tech founder; coach flags the quote as unverifiable.",
    ),
    Scenario(
        "kate.davis", "sources", "correct",
        "Product design exec cites a UX research finding in a proposal. Base AI misquotes "
        "Nielsen's 'jakob's law'; coach rewrites with the accurate framing and source.",
    ),
    Scenario(
        "tina.clark", "sources", "correct",
        "ML research lead summarizing a paper for an internal readout. Base AI paraphrases "
        "with a result claim the paper doesn't actually make; coach corrects with the paper's actual conclusion.",
    ),
    Scenario(
        "mia.anderson", "sources", "flag",
        "Designer cites a design-system statistic in a team deck. Base AI quotes a plausible "
        "but uncited figure; coach flags for verification.",
    ),

    # ─── Other (PII / scope / dangerous action) ────────────────────────
    Scenario(
        "wendy.young", "other", "correct",
        "Ops engineer pastes production logs with customer email addresses into a prompt "
        "to ask for an error pattern summary. Coach blocks the raw prompt and forwards a redacted version.",
    ),
    Scenario(
        "xander.king", "other", "correct",
        "Ops engineer asks for a one-liner to delete stale docker images. Base AI proposes "
        "`docker system prune -a -f --volumes`; coach blocks the volumes flag as too destructive for prod.",
    ),
    Scenario(
        "quinn.harris", "other", "correct",
        "Sales rep pastes a customer's internal org chart (names, titles, reporting lines) "
        "into a prompt for a talking-points draft. Coach redacts names before forwarding.",
    ),
    Scenario(
        "frank.lopez", "other", "flag",
        "Frontend engineer asks AI to 'just paste the user emails here' for a notification "
        "script. Coach flags that the emails should be fetched from the DB, not pasted, with a warning on the response.",
    ),
    Scenario(
        "bob.martinez", "other", "correct",
        "Backend engineer asks for help writing a DB migration that drops a column. Base AI "
        "drafts the DROP without any check; coach rewrites with a two-phase deprecate-then-drop migration.",
    ),
    Scenario(
        "tina.clark", "other", "flag",
        "ML research lead asks for a quick summary of an anonymized but still sensitive dataset pasted "
        "inline. Coach flags that re-identification risk exists despite anonymization.",
    ),

    # ─── A few extra factuality for volume / acceptance variety ────────
    Scenario(
        "alice.johnson", "factuality", "flag",
        "Exec asks about our cloud spend on GCP regions. Base AI confidently quotes a "
        "per-region price that's out of date; coach flags.",
    ),
    Scenario(
        "victor.hall", "efficiency", "flag",
        "ML researcher stuck in a hyperparameter-search loop. Base AI suggests trying another "
        "optimizer; coach flags that the search space is the real problem.",
    ),
]


def main():
    ap = argparse.ArgumentParser(description="Backfill coached sessions via LLM")
    ap.add_argument(
        "--count",
        type=int,
        default=len(SCENARIOS),
        help=f"Number of scenarios to run (default: all {len(SCENARIOS)})",
    )
    ap.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="pydantic-ai model id (default: %(default)s)",
    )
    ap.add_argument("--seed", type=int, default=42, help="Shuffle seed.")
    ap.add_argument(
        "--category",
        choices=["factuality", "efficiency", "sources", "other"],
        help="Only run scenarios matching this category.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate but don't write sessions to snapshot.",
    )
    args = ap.parse_args()

    rng = random.Random(args.seed)
    scenarios = list(SCENARIOS)
    if args.category:
        scenarios = [s for s in scenarios if s.category == args.category]
    rng.shuffle(scenarios)
    scenarios = scenarios[: args.count]

    print(f"Running {len(scenarios)} scenarios with {args.model}…")
    succeeded = 0
    failed: list[tuple[Scenario, Exception]] = []
    for i, sc in enumerate(scenarios, 1):
        print(f"[{i}/{len(scenarios)}] {sc.user_id} / {sc.category} / {sc.style}")
        try:
            conv, sid = generate_coached_session(
                sc.description,
                user_id=sc.user_id,
                category=sc.category,
                style=sc.style,
                model=args.model,
                write=not args.dry_run,
            )
            succeeded += 1
            print(
                f"  ✓ {conv.intervention.kind} · "
                f"util: {conv.counterfactual_utility} → {conv.utility} · "
                f"coached={len(conv.coached_events)} cf={len(conv.counterfactual_events)}"
                + (f" · sid={sid[:8]}" if sid else " · dry-run")
            )
        except Exception as e:
            failed.append((sc, e))
            print(f"  ✗ {type(e).__name__}: {e}")
        # Small jitter — be nice to the API.
        time.sleep(0.1)

    print(f"\nDone: {succeeded} succeeded, {len(failed)} failed.")
    if failed:
        print("Failures:")
        for sc, e in failed:
            print(f"  {sc.user_id}/{sc.category}/{sc.style}: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
