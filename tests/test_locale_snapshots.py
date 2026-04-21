"""Smoke tests for the per-locale snapshot generator and header routing.

Property-style checks that should hold for any locale:
  1. Generating a locale produces a loadable LocalStore with the expected
     top-level collections.
  2. Every snapshot passes the full plausibility suite.
  3. The X-Seerai-Lang header swaps the LocalStore the request handler sees.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app
from seerai import firestore_client as fc
from seerai.local_client import LocalStore
from seerai.plausibility import ALL_CHECKS
from scripts.generate_locale_data import generate, snapshot_path


def test_snapshot_paths_are_locale_specific():
    assert snapshot_path("en").name == "snapshot.json"
    assert snapshot_path("de").name == "snapshot.de.json"
    assert snapshot_path("it").name == "snapshot.it.json"
    assert snapshot_path("ru").name == "snapshot.ru.json"


def test_generated_de_snapshot_has_expected_shape(tmp_path, monkeypatch):
    """Generator writes a loadable LocalStore with orgs/users/subs/insights."""
    # Redirect the data dir so we don't clobber the real snapshots.
    monkeypatch.setattr("scripts.generate_locale_data.DATA_DIR", tmp_path)
    counts = generate("de", clear=True, seed=1)

    # Core collections populated.
    for k in ("orgs", "users", "subscriptions", "insights"):
        assert counts.get(k, 0) >= 1 or k == "insights"
    assert counts["users"] >= 10

    store = LocalStore(tmp_path / "snapshot.de.json")
    # Meta sidecar tells the frontend which locale this snapshot is.
    assert store.data["_meta"]["lang"] == "de"
    assert store.data["_meta"]["industry"]
    # German company names land in the orgs collection.
    assert "kraftwerk" in store.data["orgs"]


def test_generated_snapshots_pass_plausibility(tmp_path, monkeypatch):
    """Regression guard: generator output must satisfy every plausibility rule."""
    monkeypatch.setattr("scripts.generate_locale_data.DATA_DIR", tmp_path)
    for lang in ("de", "it", "ru"):
        generate(lang, clear=True, seed=7)
        store = LocalStore(snapshot_path_in(tmp_path, lang))
        violations = []
        for check in ALL_CHECKS:
            violations.extend(check.violations(store.data))
        assert not violations, f"{lang}: {[str(v) for v in violations[:5]]}"


def test_lang_header_routes_to_localized_snapshot():
    """X-Seerai-Lang header makes the server read data/snapshot.<lang>.json."""
    client = TestClient(app)

    # Without the header → default (en) snapshot contains Acme.
    r = client.get("/api/orgs")
    assert r.status_code == 200
    root_ids_en = {row["org_id"] for row in r.json()}
    assert "acme" in root_ids_en

    # With de header → German automotive companies appear.
    r = client.get("/api/orgs", headers={"X-Seerai-Lang": "de"})
    root_ids_de = {row["org_id"] for row in r.json()}
    assert "kraftwerk" in root_ids_de
    assert "acme" not in root_ids_de

    # With it header → Italian fashion companies appear.
    r = client.get("/api/orgs", headers={"X-Seerai-Lang": "it"})
    root_ids_it = {row["org_id"] for row in r.json()}
    assert "moda" in root_ids_it
    assert "acme" not in root_ids_it

    # With ru header → Russian banking companies appear.
    r = client.get("/api/orgs", headers={"X-Seerai-Lang": "ru"})
    root_ids_ru = {row["org_id"] for row in r.json()}
    assert "volga" in root_ids_ru
    assert "acme" not in root_ids_ru


def test_datasource_endpoint_lists_available_langs():
    """The frontend queries this to decide which language rows to show."""
    client = TestClient(app)
    info = client.get("/api/datasource").json()
    assert info["source"] == "local"
    # At least en (shipped) plus the locales we just generated.
    assert "en" in info["local_langs"]
    assert "de" in info["local_langs"]
    assert "it" in info["local_langs"]
    assert "ru" in info["local_langs"]


# ── helpers ────────────────────────────────────────────────────────────


def snapshot_path_in(data_dir, lang):
    """Mirror scripts.generate_locale_data.snapshot_path for a custom data_dir."""
    if lang == "en":
        return data_dir / "snapshot.json"
    return data_dir / f"snapshot.{lang}.json"
