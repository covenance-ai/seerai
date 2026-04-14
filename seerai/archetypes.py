"""Archetype sessions — reference sessions with real events for demo purposes.

Empty mock sessions are mapped to the closest archetype by (provider, utility).
The session detail endpoint serves the archetype's events when a session has none.
"""

from __future__ import annotations

# Each archetype: (user_id, session_id) of a session with real events.
# Covers the main provider × utility combinations.
ARCHETYPES: dict[tuple[str, str], tuple[str, str]] = {
    ("anthropic", "useful"): ("bob.martinez", "48b3f621-65d2-4436-ad3d-a2e02e6f59e7"),
    ("openai", "useful"): ("bob.martinez", "4dca0993-2919-451d-a9f4-0601e0343dc8"),
    ("google", "trivial"): ("bob.martinez", "359ad347-a2e0-45fa-b655-daa6da81f1ce"),
    ("mistral", "non_work"): ("grace.patel", "2fe4d45a-9115-43ef-89df-5647350e4e58"),
    ("anthropic", "trivial"): ("carol.chen", "99375cd4-6cd0-4d73-b68e-d040a6218eea"),
}

# Fallback chain: try (provider, utility), then (any, utility), then first archetype.
_BY_UTILITY: dict[str, tuple[str, str]] = {}
_DEFAULT: tuple[str, str] = list(ARCHETYPES.values())[0]

for (prov, util), ref in ARCHETYPES.items():
    _BY_UTILITY.setdefault(util, ref)


def match_archetype(provider: str | None, utility: str | None) -> tuple[str, str]:
    """Return (user_id, session_id) of the best-matching archetype."""
    key = (provider or "", utility or "")
    if key in ARCHETYPES:
        return ARCHETYPES[key]
    if utility and utility in _BY_UTILITY:
        return _BY_UTILITY[utility]
    return _DEFAULT
