"""Translate the English string catalog into a target language via pydantic-ai.

Reads `seerai/static/i18n/en.json`, sends the values to a fast LLM in batches,
and writes `<lang>.json` alongside. Preserves HTML/JSX placeholders verbatim so
existing span IDs and inline structure still work after translation.

Usage:
    uv run python -m scripts.i18n_translate de
    uv run python -m scripts.i18n_translate it
    uv run python -m scripts.i18n_translate de it --model openai:gpt-4o-mini
    uv run python -m scripts.i18n_translate de --force   # overwrite existing
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = ROOT / "seerai" / "static" / "i18n"
EN_PATH = CATALOG_DIR / "en.json"

LANG_NAMES = {
    "de": "German (Deutsch)",
    "it": "Italian (Italiano)",
    "fr": "French (Français)",
    "es": "Spanish (Español)",
}

DEFAULT_MODEL = "google-gla:gemini-3.1-pro-preview"


class Translation(BaseModel):
    """One English → target-language pair."""

    source: str = Field(description="The original English string, verbatim.")
    target: str = Field(description="The translated string.")


class TranslationBatch(BaseModel):
    """The full batch returned by the LLM."""

    translations: list[Translation]


_GLOSSARY = {
    "de": {
        "session": "Sitzung (NOT 'Session' — always translate)",
        "sessions": "Sitzungen",
        "my sessions": "Meine Sitzungen",
        "coach": "Coach (keep as-is — established term)",
        "coached": "begleitet (by the coach)",
        "intervention": "Eingriff",
        "utility": "Nutzen",
        "useful": "nützlich",
        "trivial": "trivial",
        "non-work": "außerberuflich",
        "harmful": "schädlich",
        "paygrade": "Gehaltsstufe",
        "above paygrade": "über Gehaltsstufe",
        "below paygrade": "unter Gehaltsstufe",
        "cross-department": "abteilungsübergreifend",
        "counterfactual": "kontrafaktisch",
        "insights": "Insights (or 'Erkenntnisse' — pick one and stick to it)",
        "dashboard": "Dashboard (keep as-is)",
        "factuality": "Faktentreue",
        "efficiency": "Effizienz",
        "sources": "Quellen",
        "privacy mode": "Datenschutzmodus",
        "support review": "Support-Prüfung",
    },
    "it": {
        "session": "sessione",
        "sessions": "sessioni",
        "my sessions": "Le mie sessioni",
        "coach": "Coach (keep as-is)",
        "coached": "coachato / con coach",
        "intervention": "intervento",
        "utility": "utilità",
        "useful": "utile",
        "trivial": "banale",
        "non-work": "non lavorativo",
        "harmful": "dannoso",
        "paygrade": "livello retributivo",
        "above paygrade": "sopra il livello retributivo",
        "below paygrade": "sotto il livello retributivo",
        "cross-department": "interdipartimentale",
        "counterfactual": "controfattuale",
        "insights": "insight (or 'approfondimenti' — pick one and stick to it)",
        "dashboard": "dashboard (keep as-is)",
        "factuality": "fattualità",
        "efficiency": "efficienza",
        "sources": "fonti",
        "privacy mode": "modalità privacy",
        "support review": "revisione del supporto",
    },
}


def _system_prompt(lang: str, lang_name: str) -> str:
    gloss = _GLOSSARY.get(lang, {})
    gloss_lines = "\n".join(f"  - {en!r} → {tr}" for en, tr in gloss.items())
    return f"""You translate UI strings for a corporate LLM observability
dashboard (product name: seerai). Translate each English source string
into {lang_name}.

STRICT FORMATTING RULES:
- Keep HTML tags, attributes, and entities (&amp;, &mdash;, …) byte-for-byte identical.
- Keep interpolation placeholders ({{variable}}, $var, %s, ${{varName}}) identical.
- Keep inline tokens like <span id="min-cohort-inline">N</span> exactly as they appear.
- Keep URLs, file paths, CSS class names, and element IDs unchanged.
- Keep acronyms (ROI, API, LLM, AI, GDPR, KPI) unchanged.
- Preserve trailing punctuation, ellipses (… vs ...), and the em dash (—).
- Return every source string exactly once, matching `source` character-for-character.

TRANSLATION QUALITY RULES:
- Use the product glossary below consistently. If the glossary says
  "session" → "Sitzung", then "My Sessions" MUST translate to "Meine
  Sitzungen", never "Meine Sessions". Anglicisms are only acceptable
  when the glossary explicitly marks them "keep as-is".
- When the same English word appears in several strings, translate it
  the same way every time.
- Prefer natural, native-sounding phrasing over literal word-for-word
  translation. Read each output aloud — if a native speaker wouldn't
  say it that way in business software, rephrase.
- Page titles that start with "seerai — X": translate X to the target
  language but keep the em dash and "seerai" intact.

DOMAIN GLOSSARY ({lang}):
{gloss_lines}

Other domain terms:
- "observer LLM" = a separate LLM watching the user's primary chat
- "flag / flagged" = user-marked for seer.ai review (not "Flagge")
- "rollup / rollups" = aggregated metrics
"""


def _translate(strings: list[str], *, lang: str, model: str) -> dict[str, str]:
    try:
        from pydantic_ai import Agent
    except ImportError as e:
        raise RuntimeError(
            "pydantic-ai not installed. Run: uv sync --extra generate"
        ) from e

    lang_name = LANG_NAMES.get(lang, lang)
    agent = Agent(
        model,
        output_type=TranslationBatch,
        system_prompt=_system_prompt(lang, lang_name),
    )

    # Feed the LLM a numbered list — structured output already covers pairing,
    # but the indices make mis-alignments easy to spot in failures.
    numbered = "\n".join(
        f"{i + 1}. {json.dumps(s, ensure_ascii=False)}" for i, s in enumerate(strings)
    )
    prompt = (
        f"Translate these {len(strings)} UI strings to {lang_name}. "
        f"Return one Translation entry per line, preserving `source` verbatim.\n\n"
        f"{numbered}"
    )

    result = agent.run_sync(prompt).output
    by_source = {tr.source: tr.target for tr in result.translations}

    missing = [s for s in strings if s not in by_source]
    if missing:
        # Don't silently drop — escalate so we know the batch size was too big.
        preview = missing[:5]
        raise RuntimeError(
            f"{lang}: LLM skipped {len(missing)} strings; first few: {preview}"
        )

    return {s: by_source[s] for s in strings}


def _batched(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def translate_language(
    lang: str, *, model: str = DEFAULT_MODEL, batch_size: int = 60, force: bool = False
) -> Path:
    out = CATALOG_DIR / f"{lang}.json"
    if out.exists() and not force:
        existing = json.loads(out.read_text())
    else:
        existing = {}

    en = json.loads(EN_PATH.read_text())
    todo = [s for s in en.keys() if s not in existing]
    if not todo:
        print(f"{lang}: already translated ({len(en)} entries).")
        return out

    print(
        f"{lang}: translating {len(todo)} strings "
        f"({len(existing)} already present) via {model}…"
    )

    translated = dict(existing)
    for i, batch in enumerate(_batched(todo, batch_size), 1):
        print(f"  batch {i}: {len(batch)} strings")
        translated.update(_translate(batch, lang=lang, model=model))

    # Deterministic key ordering matches en.json so diffs are tidy.
    ordered = {k: translated[k] for k in en.keys() if k in translated}
    out.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n")
    print(f"  wrote {out.relative_to(ROOT)}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("languages", nargs="+", help="Target languages (e.g. de it)")
    ap.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"pydantic-ai model id (default: {DEFAULT_MODEL})",
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=60,
        help="Strings per LLM call. Smaller is safer, larger is faster.",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Retranslate every key, ignoring existing entries.",
    )
    args = ap.parse_args()

    for lang in args.languages:
        translate_language(
            lang, model=args.model, batch_size=args.batch_size, force=args.force
        )


if __name__ == "__main__":
    main()
