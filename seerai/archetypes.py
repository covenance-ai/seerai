"""Archetype sessions — reference sessions with real events for demo purposes.

Every snapshot (English, German, Italian, …) ships a handful of full-event
archetype sessions. Stub sessions with no events fall back to the
closest archetype by ``(provider, utility)`` so the session-detail page
always has plausible, locale-appropriate content.

The archetype index is built lazily on first use per local snapshot and
cached on the client instance, so language switches (which swap the
underlying LocalStore) automatically get a fresh index.
"""

from __future__ import annotations


def _build_archetype_index(db) -> dict[tuple[str, str], tuple[str, str]]:
    """Scan the given client and return ``(provider, utility) → (uid, sid)``.

    We consider a session an "archetype" when it has events stored — that's
    the only way the detail endpoint actually serves content. Walks all
    users/sessions, keeps the first full-event session per
    ``(provider, utility)`` pair.
    """
    index: dict[tuple[str, str], tuple[str, str]] = {}
    for user_doc in db.collection("users").stream():
        uid = user_doc.id
        sessions = (
            db.collection("users").document(uid).collection("sessions").stream()
        )
        for sess_doc in sessions:
            sess = sess_doc.to_dict() or {}
            sid = sess_doc.id
            events_path = f"users/{uid}/sessions/{sid}/events"
            # Fast path for LocalStore — check the underlying dict.
            events = getattr(db, "data", {}).get(events_path, {})
            if not events:
                # Firestore path — actually stream events to check presence.
                has_any = any(
                    True
                    for _ in db.collection("users")
                    .document(uid)
                    .collection("sessions")
                    .document(sid)
                    .collection("events")
                    .limit(1)
                    .stream()
                )
                if not has_any:
                    continue
            key = (sess.get("provider") or "", sess.get("utility") or "")
            index.setdefault(key, (uid, sid))
    return index


def _get_index(db) -> dict[tuple[str, str], tuple[str, str]]:
    """Cached per-db lookup. Works for LocalStore (mutable) and Firestore."""
    cache = getattr(db, "_archetype_index", None)
    if cache is None:
        cache = _build_archetype_index(db)
        try:
            db._archetype_index = cache  # store on the client for reuse
        except AttributeError:
            # Some clients may be immutable; just skip caching.
            pass
    return cache


def match_archetype(
    provider: str | None, utility: str | None
) -> tuple[str, str] | None:
    """Return ``(user_id, session_id)`` of the best-matching archetype.

    Returns None if the current data source has no full-event sessions at
    all — callers should treat that as "no fallback content, render empty".
    """
    from seerai.firestore_client import get_firestore_client

    db = get_firestore_client()
    index = _get_index(db)
    if not index:
        return None

    # Exact (provider, utility) match wins.
    exact = index.get((provider or "", utility or ""))
    if exact:
        return exact

    # Same utility across any provider.
    if utility:
        for (_, util), ref in index.items():
            if util == utility:
                return ref

    # Same provider across any utility.
    if provider:
        for (prov, _), ref in index.items():
            if prov == provider:
                return ref

    # Fall back to the first archetype we built.
    return next(iter(index.values()))


# Back-compat shim: external callers imported ARCHETYPES as a dict. Leave a
# lazy view that builds it on access from the current snapshot.
def __getattr__(name: str):
    if name == "ARCHETYPES":
        from seerai.firestore_client import get_firestore_client

        return _get_index(get_firestore_client())
    raise AttributeError(name)
