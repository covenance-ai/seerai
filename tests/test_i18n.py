"""Tests for the i18n pipeline.

Covers:
- Catalog extraction: idempotent on re-run, no new keys introduced by a
  second pass over already-marked HTML.
- Code-marker filter: JS template strings inside <script> blocks don't leak
  into the HTML catalog.
- Translated bundles: de.json / it.json (when present) cover every key in
  en.json, and translations preserve the placeholders the app relies on
  (HTML tags, element IDs, `${…}` interpolations).
- Extracted HTML: every data-i18n element's text, and every data-i18n-html
  element's innerHTML (normalized) is a key in en.json, so the runtime
  can always find a translation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts import i18n_extract

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "seerai" / "dashboard" / "pages"
CATALOG_DIR = ROOT / "seerai" / "static" / "i18n"
EN = CATALOG_DIR / "en.json"


def _load(path: Path) -> dict[str, str]:
    return json.loads(path.read_text())


def test_en_catalog_present_and_identity() -> None:
    """en.json exists and every value equals its key.

    The catalog uses the English string as both key and value so `t(s)` in
    English is a no-op; if a future edit ever diverges key/value by accident
    this test catches it.
    """
    assert EN.exists(), "Run `python -m scripts.i18n_extract` to generate it."
    cat = _load(EN)
    assert cat, "catalog is empty"
    for key, value in cat.items():
        assert key == value, f"en.json has non-identity entry for {key!r}"


def test_extractor_is_idempotent(tmp_path: Path) -> None:
    """Running the extractor twice doesn't add new keys or re-mark elements.

    Regression guard: the rewriter used to re-wrap elements that already
    carried data-i18n when the attribute spelling drifted between runs.
    """
    # Seed a tmp pages dir with a copy of one real page so the test exercises
    # the exact rewriter logic against realistic markup.
    src_page = PAGES / "admin.html"
    dst = tmp_path / "admin.html"
    dst.write_text(src_page.read_text())

    catalog: dict[str, str] = {}
    i18n_extract._rewrite_file(dst, catalog)
    after_one = dst.read_text()
    keys_one = set(catalog.keys())

    # Write the first-pass result and run again on the marked-up output.
    dst.write_text(after_one)
    catalog2: dict[str, str] = dict(catalog)
    i18n_extract._rewrite_file(dst, catalog2)
    after_two = dst.read_text()

    assert after_one == after_two, "second pass mutated an already-marked file"
    assert set(catalog2.keys()) == keys_one, "second pass invented new keys"


def test_extractor_skips_script_blocks() -> None:
    """JS template literals inside <script> don't become HTML-catalog keys.

    Regression: we once captured `${esc(ins.title)}` into the catalog.
    """
    catalog = _load(EN)
    for key in catalog:
        assert "${" not in key, f"JS template literal leaked into catalog: {key!r}"
        assert "esc(" not in key, f"JS expression leaked into catalog: {key!r}"


def test_marked_html_has_catalog_entries() -> None:
    """Every data-i18n text and every data-i18n-html body is a catalog key.

    This is the runtime invariant: when the DOM walker finds a marker, it
    must find a matching translation (or the English key as fallback). A
    missing key would still render, but it indicates a broken build.
    """
    catalog = _load(EN)

    text_re = re.compile(
        r"<([a-zA-Z0-9]+)([^<>]*?)\bdata-i18n\b([^<>]*?)>([^<]*)</\1>",
        re.DOTALL,
    )
    html_re = re.compile(
        r"<([a-zA-Z0-9]+)([^<>]*?)\bdata-i18n-html\b([^<>]*?)>(.*?)</\1>",
        re.DOTALL,
    )

    for page in sorted(PAGES.glob("*.html")):
        src = page.read_text()
        for m in text_re.finditer(src):
            key = i18n_extract._normalize(m.group(4))
            if not key:
                continue
            assert key in catalog, f"{page.name}: data-i18n text {key!r} not in en.json"

        for m in html_re.finditer(src):
            key = i18n_extract._normalize(m.group(4))
            if not key:
                continue
            # The runtime matches normalized innerHTML against the catalog.
            assert key in catalog, (
                f"{page.name}: data-i18n-html body {key[:60]!r}… not in en.json"
            )


@pytest.mark.parametrize("lang", ["de", "it"])
def test_translated_bundle_covers_every_en_key(lang: str) -> None:
    bundle_path = CATALOG_DIR / f"{lang}.json"
    if not bundle_path.exists():
        pytest.skip(f"{lang}.json not yet generated")

    en = _load(EN)
    bundle = _load(bundle_path)
    missing = set(en) - set(bundle)
    assert not missing, (
        f"{lang} bundle is missing {len(missing)} keys; first few: {list(missing)[:3]}"
    )


@pytest.mark.parametrize("lang", ["de", "it"])
def test_translations_preserve_placeholders(lang: str) -> None:
    """Every `${…}` and known element-id `<span id="…">` in an English value
    must survive verbatim in the translation.

    We don't check every tag — that would punish legitimate reordering —
    but placeholders and stable element IDs are load-bearing. Translating
    `${fmtNum(x)}` to something else would break interpolation at runtime.
    """
    bundle_path = CATALOG_DIR / f"{lang}.json"
    if not bundle_path.exists():
        pytest.skip(f"{lang}.json not yet generated")

    en = _load(EN)
    bundle = _load(bundle_path)

    for key, translated in bundle.items():
        en_value = en.get(key)
        if en_value is None:
            continue
        placeholders = set(re.findall(r"\$\{[^}]+\}", en_value))
        for p in placeholders:
            assert p in translated, (
                f"{lang}: placeholder {p!r} dropped in translation of {key!r}"
            )

        # IDs we query by JS (min-cohort-inline, company-badge, …) must survive.
        ids = set(re.findall(r'id="([^"]+)"', en_value))
        for i in ids:
            assert f'id="{i}"' in translated, (
                f"{lang}: id={i!r} dropped in translation of {key!r}"
            )


def test_no_local_t_shadowing_in_page_scripts() -> None:
    """No inline `<script>` block may declare a local variable named ``t``.

    Regression: ``my_sessions.html`` and ``sessions.html`` both had
    ``const t = new Date(...).toLocaleString()`` inside a ``for`` loop that
    also called ``t('hr saved')`` a few lines later. The const shadowed the
    global translator, so rows with non-zero dollar value threw
    ``TypeError: t is not a function`` — only visible in environments with
    real (useful/harmful) sessions. The catch handler then rendered its own
    ``t('Error:')`` call successfully, which made the symptom look random.

    Cheap structural check: the name ``t`` is reserved for the global
    translator inside page ``<script>`` blocks. Rename locals (``ts`` etc.).
    """
    script_re = re.compile(r"<script\b[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)
    decl_re = re.compile(r"\b(?:const|let|var)\s+t\b\s*=")

    offenders: list[str] = []
    for page in sorted(PAGES.glob("*.html")):
        src = page.read_text()
        for m in script_re.finditer(src):
            body = m.group(1)
            if decl_re.search(body):
                offenders.append(page.name)
                break

    assert not offenders, (
        f"pages shadow the global `t` translator with a local binding: "
        f"{offenders}. Rename the local (e.g. `const ts = ...`)."
    )


def test_i18n_runtime_source_well_formed() -> None:
    """Sanity-check i18n.js: it exposes the globals the dashboard relies on."""
    src = (ROOT / "seerai" / "static" / "i18n.js").read_text()
    for needle in (
        "window.t = t",
        "window.seerai.applyI18n",
        "window.seerai.setLang",
        "window.seerai.getLang",
        "data-i18n-html",
        "data-i18n-attrs",
    ):
        assert needle in src, f"i18n.js missing expected hook: {needle!r}"
