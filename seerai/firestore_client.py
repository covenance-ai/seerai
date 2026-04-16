"""Firestore / LocalStore client provider.

The default backend is the real Firestore database (project
``GCP_PROJECT``, database ``FIRESTORE_DATABASE``). Set
``DATA_SOURCE=local`` to use the duck-typed ``LocalStore`` pointed at
``data/snapshot.json`` for demo / offline / test modes.

**Localized local snapshots**

The dashboard supports a language toggle (``en`` / ``de`` / ``it``). When
"local" data source is selected, the client picks one of:

  - ``data/snapshot.json``       (en — kept at legacy filename)
  - ``data/snapshot.de.json``    (de)
  - ``data/snapshot.it.json``    (it)

The language is read from a ContextVar populated by the FastAPI middleware
in ``main.py`` from the ``X-Seerai-Lang`` request header. Outside of a
request (CLI, tests), it defaults to ``en`` or whatever ``SEERAI_LANG`` is
set to.

Firestore data source is not localized — one live DB for all languages.
"""

import os
from contextvars import ContextVar
from pathlib import Path

from seerai.local_client import LocalStore

_source: str | None = None  # None = auto-detect
# Keyed by resolved snapshot path string — path-keyed so tests that swap
# LOCAL_DATA_PATH or switch languages mid-run don't hit a stale client.
_local_clients: dict[str, LocalStore] = {}
_firestore_client = None
# Test override — when set, `get_firestore_client()` returns this directly
# instead of resolving by lang. Kept for backward compatibility with the
# pre-locale test fixtures that do `monkeypatch.setattr(fc, "_client", ...)`.
_client = None

_DATA_DIR = Path(__file__).parent.parent / "data"
SNAPSHOT_PATH = _DATA_DIR / "snapshot.json"

# Set by the FastAPI middleware (seerai.middleware.locale). Outside a
# request it falls back to SEERAI_LANG or "en".
current_lang: ContextVar[str | None] = ContextVar("current_lang", default=None)

SUPPORTED_LANGS = ("en", "de", "it")


def _resolve_lang() -> str:
    lang = current_lang.get()
    if lang and lang in SUPPORTED_LANGS:
        return lang
    env = os.getenv("SEERAI_LANG")
    if env and env in SUPPORTED_LANGS:
        return env
    return "en"


def snapshot_path_for(lang: str) -> Path:
    """Return the snapshot file path for a given language.

    English keeps the legacy path so existing tooling / URLs work
    unchanged. Non-English locales get ``snapshot.<lang>.json``.
    """
    override = os.getenv("LOCAL_DATA_PATH")
    if override and lang == "en":
        # Honour LOCAL_DATA_PATH for the default locale only — it's used by
        # tests and dev overrides and always points at "the current data".
        return Path(override)
    if lang == "en":
        return SNAPSHOT_PATH
    return _DATA_DIR / f"snapshot.{lang}.json"


def snapshot_exists(lang: str | None = None) -> bool:
    """Is there a local snapshot file for this language?"""
    lang = lang or _resolve_lang()
    return snapshot_path_for(lang).exists()


def available_langs() -> list[str]:
    """List language codes that have a local snapshot on disk."""
    return [lang for lang in SUPPORTED_LANGS if snapshot_path_for(lang).exists()]


def get_datasource() -> str:
    """Return current data source: 'local' or 'firestore'.

    Defaults to ``firestore``; set ``DATA_SOURCE=local`` (or call
    :func:`set_datasource`) to opt into the snapshot-backed demo/dev mode.
    """
    if _source:
        return _source
    env = os.getenv("DATA_SOURCE")
    if env:
        return env
    return "firestore"


def set_datasource(source: str) -> None:
    """Switch data source at runtime. Resets client singletons."""
    global _firestore_client, _source
    _source = source
    # Drop caches so the next call re-resolves both path & lang.
    _firestore_client = None
    _local_clients.clear()


def get_firestore_client():
    """Return a Firestore-shaped client honoring the current lang (local only)."""
    global _firestore_client
    # Test-only override wins.
    if _client is not None:
        return _client
    source = get_datasource()
    if source == "local":
        lang = _resolve_lang()
        path = snapshot_path_for(lang)
        # Fall back to English snapshot if the requested lang is missing
        # — better to show English content than crash a language toggle.
        if not path.exists() and lang != "en":
            path = snapshot_path_for("en")
        key = str(path.resolve()) if path.exists() else str(path)
        client = _local_clients.get(key)
        if client is None:
            client = LocalStore(path)
            _local_clients[key] = client
        return client

    if _firestore_client is None:
        from google.cloud.firestore import Client

        project = os.getenv("GCP_PROJECT", "covenance-469421")
        database = os.getenv("FIRESTORE_DATABASE", "seerai")
        _firestore_client = Client(project=project, database=database)
    return _firestore_client


# ── Test backward-compat shim ────────────────────────────────────────────
# Older tests set ``fc._client = None`` to bust the singleton. Keep that
# working by providing a `_client` attribute whose setter clears the cache.
class _ClientHandle:
    def __get__(self, instance, owner):
        return None

    def __set__(self, instance, value):
        if value is None:
            _local_clients.clear()
            globals()["_firestore_client"] = None


# Modules don't support __setattr__; we expose a module function for tests.
def reset_clients() -> None:
    """Drop all cached clients. Call this from tests that swap snapshots."""
    global _firestore_client
    _local_clients.clear()
    _firestore_client = None
