"""Scan dashboard HTML pages and tag translatable elements in place.

For each page we:
  1. Find elements from a small whitelist (`h1`..`h4`, `p`, `button`, ...) that
     contain plain text and inject a `data-i18n` attribute on their opening tag.
  2. For elements with mixed text + inline HTML (a `<p>` wrapping a `<span>`,
     for instance), inject `data-i18n-html` so the runtime translates the
     whole inner HTML blob as a single key.
  3. Collect every English string we marked into an `en.json` catalog.

The rewriter is intentionally idempotent: elements that already have either
marker are left alone, so it's safe to re-run as the dashboard grows.

Usage:
    uv run python -m scripts.i18n_extract
    uv run python -m scripts.i18n_extract --dry-run    # print plan, change nothing
"""

from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "seerai" / "dashboard" / "pages"
STATIC = ROOT / "seerai" / "static"
CATALOG_PATH = STATIC / "i18n" / "en.json"

# Tags whose simple-text content we treat as translatable.
# Keep this tight — translating every <span> turns UI chrome into noise.
TEXT_TAGS = (
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "p",
    "label",
    "button",
    "th",
    "option",
    "summary",
    "li",
    "caption",
)

# Whole-innerHTML tags: these often wrap a sentence with an inline <span> or
# <kbd>. When we spot inline HTML we use data-i18n-html so the translator can
# keep the placeholder intact.
HTML_TAGS = ("p", "h1", "h2", "h3", "h4", "li", "summary")

# Simple text also worth catching when it's the ONLY child of these tags.
DIV_LIKE_TAGS = ("div", "span")


# Opening-tag regex: matches `<tag ...>` or `<tag>` without self-closing.
# Captures: (1) full tag attributes block (may be empty).
def _open_tag_re(tag: str) -> re.Pattern:
    return re.compile(
        rf"<{tag}(\s+[^<>]*?)?>",
        re.IGNORECASE | re.DOTALL,
    )


@dataclass
class Rewrite:
    path: Path
    original: str
    updated: str
    keys_added: list[str] = field(default_factory=list)
    html_keys_added: list[str] = field(default_factory=list)


_SUBSTANTIVE_RE = re.compile(r"[A-Za-zÀ-ÿ]")
_ALL_PUNCT_RE = re.compile(r"^[\s\W_]+$")


def _is_translatable(text: str) -> bool:
    """Is this text worth a translation entry?

    Ignore empty strings, pure punctuation ("—", "·", "/"), and short tokens
    that are IDs or symbols. Anything with at least two letters qualifies.
    """
    s = text.strip()
    if not s:
        return False
    if _ALL_PUNCT_RE.match(s):
        return False
    letters = len(_SUBSTANTIVE_RE.findall(s))
    return letters >= 2


def _normalize(text: str) -> str:
    """Collapse internal whitespace — the runtime does the same for keys."""
    return re.sub(r"\s+", " ", text).strip()


def _has_i18n_attr(attrs: str) -> bool:
    return bool(re.search(r"\bdata-i18n(?:-html|-attrs)?\b", attrs or ""))


def _insert_attr(open_tag: str, attr_name: str, attr_value: str | None = None) -> str:
    """Add `attr_name` (optionally `="value"`) to an opening tag string."""
    assert open_tag.startswith("<") and open_tag.endswith(">")
    body = open_tag[1:-1]
    token = (
        attr_name
        if attr_value is None
        else f'{attr_name}="{html.escape(attr_value, quote=True)}"'
    )
    # Stick it right after the tag name, before any existing attributes —
    # this keeps our added attr close to the opening `<` for easy spotting
    # in diffs.
    parts = body.split(None, 1)
    if len(parts) == 1:
        return f"<{parts[0]} {token}>"
    return f"<{parts[0]} {token} {parts[1]}>"


def _find_matching_close(src: str, tag: str, start: int) -> int | None:
    """Return the index of the `</tag>` that closes the element opened at `start`.

    Handles nested same-tag elements. Returns None if no matching close exists.
    """
    open_re = re.compile(rf"<{tag}\b", re.IGNORECASE)
    close_re = re.compile(rf"</{tag}\s*>", re.IGNORECASE)
    depth = 1
    i = start
    while i < len(src):
        m_close = close_re.search(src, i)
        if not m_close:
            return None
        m_open = open_re.search(src, i, m_close.start())
        if m_open:
            depth += 1
            i = m_open.end()
            continue
        depth -= 1
        if depth == 0:
            return m_close.start()
        i = m_close.end()
    return None


def _contains_inline_html(inner: str) -> bool:
    # Returns True if the element's inner content contains child tags
    # (anything other than text). We don't count HTML entities.
    return bool(re.search(r"<[^/!][^>]*>", inner))


_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL
)
# Substrings that betray a JS template expression slipping into our regex.
# If any of these appear, the "text" we grabbed is actually code — skip.
_CODE_MARKERS = ("${", "' +", '" +', "+ '", '+ "', "<svg", "esc(")


def _has_code_markers(s: str) -> bool:
    return any(m in s for m in _CODE_MARKERS)


def _mask_scripts(src: str) -> tuple[str, list[tuple[int, int, str]]]:
    """Replace <script>…</script> / <style>…</style> bodies with blank space.

    Returns the masked source and a list of (start, end, original) blocks so
    we can restore the originals byte-for-byte after the rewrite pass.
    """
    masks: list[tuple[int, int, str]] = []

    def _sub(m: re.Match) -> str:
        masks.append((m.start(), m.end(), m.group(0)))
        # Replace inner content with spaces of equal length so positions stay
        # stable for regex scanning, and leave the opening/closing tags intact.
        orig = m.group(0)
        # Find the `>` that ends the opening tag and the `<` that starts the
        # closing tag.
        open_end = orig.index(">") + 1
        close_start = orig.rindex("<")
        inner = orig[open_end:close_start]
        return orig[:open_end] + (" " * len(inner)) + orig[close_start:]

    masked = _SCRIPT_STYLE_RE.sub(_sub, src)
    return masked, masks


# Regexes for harvesting keys from elements that are ALREADY marked up
# (hand-authored or from a previous run of this script). Without these we
# lose any translation keys someone added by hand — the test suite catches
# the resulting catalog hole.
_EXISTING_TEXT_RE = re.compile(
    r"<([a-zA-Z0-9]+)(?:\s[^<>]*)?\bdata-i18n\b(?:\s[^<>]*)?>([^<]*)</\1>",
    re.DOTALL,
)
_EXISTING_HTML_RE = re.compile(
    r"<([a-zA-Z0-9]+)(?:\s[^<>]*)?\bdata-i18n-html\b(?:\s[^<>]*)?>(.*?)</\1>",
    re.DOTALL,
)


def _harvest_existing_markers(src: str, catalog: dict[str, str]) -> None:
    """Add keys for `data-i18n` / `data-i18n-html` elements already in the file.

    Runs BEFORE the rewrite pass. The rewrite skips already-marked elements
    for idempotency, so without this step hand-authored markers would never
    make it into en.json.
    """
    for m in _EXISTING_TEXT_RE.finditer(src):
        key = _normalize(m.group(2))
        if _is_translatable(key) and not _has_code_markers(key):
            catalog.setdefault(key, key)

    for m in _EXISTING_HTML_RE.finditer(src):
        key = _normalize(m.group(2))
        # data-i18n-html keys are the full innerHTML; code markers in the
        # inner text usually mean a JS template slipped through.
        if _has_code_markers(key):
            continue
        stripped = re.sub(r"<[^>]+>", "", key)
        if _is_translatable(stripped):
            catalog.setdefault(key, key)


def _rewrite_file(path: Path, catalog: dict[str, str]) -> Rewrite:
    original = path.read_text()
    # We run the regex rewrite on a version where script/style bodies are
    # blanked out, then merge the injected attrs back into the original. This
    # avoids the extractor mistaking JS template literals for HTML text.
    masked, _ = _mask_scripts(original)
    src = masked

    # Harvest keys from elements that are already marked up — the rewrite
    # pass below would skip them for idempotency.
    _harvest_existing_markers(masked, catalog)

    keys_added: list[str] = []
    html_keys_added: list[str] = []

    # Walk tags in a stable order so re-runs produce identical diffs.
    for tag in TEXT_TAGS:
        src, added_text, added_html = _tag_pass(src, tag, catalog)
        keys_added.extend(added_text)
        html_keys_added.extend(added_html)

    # Reconstruct the final text. The rewrite only inserted attributes into
    # opening tags in the masked region, and those are outside script/style
    # bodies. We produce the final file by taking the masked-and-rewritten
    # outer HTML and restoring the original bodies of each script/style block.
    updated = _unmask(src, original)

    # <title> lives in <head>; the runtime doesn't translate it, but we still
    # want it in the catalog so translators know about the page title.
    for m in re.finditer(r"<title>([^<]+)</title>", updated, re.IGNORECASE):
        text = _normalize(m.group(1))
        if _is_translatable(text):
            catalog.setdefault(text, text)

    return Rewrite(
        path=path,
        original=original,
        updated=updated,
        keys_added=keys_added,
        html_keys_added=html_keys_added,
    )


def _unmask(rewritten_masked: str, original: str) -> str:
    """Re-insert original `<script>`/`<style>` bodies into the rewritten source.

    `rewritten_masked` is the source we edited with attribute injections; its
    script/style INNER regions are blanks but its tags line up. Walk both
    strings together, copying from `rewritten_masked` outside script/style
    and from `original` inside.
    """
    # We iterate over script/style blocks in both sources in lockstep,
    # copying from rewritten_masked between blocks and from original inside
    # them. Rewrites only added attributes outside script/style, so the
    # block count lines up.
    out: list[str] = []
    orig_blocks = list(_SCRIPT_STYLE_RE.finditer(original))
    rewritten_blocks = list(_SCRIPT_STYLE_RE.finditer(rewritten_masked))
    if len(orig_blocks) != len(rewritten_blocks):
        # Shouldn't happen — blanking preserved the tags. Fall back to the
        # rewritten text so we at least don't lose the i18n markers.
        return rewritten_masked

    pos_r = 0
    for om, rm in zip(orig_blocks, rewritten_blocks):
        out.append(rewritten_masked[pos_r : rm.start()])
        out.append(om.group(0))
        pos_r = rm.end()
    out.append(rewritten_masked[pos_r:])
    return "".join(out)


def _tag_pass(
    src: str, tag: str, catalog: dict[str, str]
) -> tuple[str, list[str], list[str]]:
    """Single-tag sweep.

    Iterates over every `<tag …>` in `src`, resolves its closing `</tag>`,
    inspects the inner content, and rewrites the opening tag to carry an
    `data-i18n` or `data-i18n-html` marker when the text qualifies.
    """
    open_re = _open_tag_re(tag)
    keys_added: list[str] = []
    html_keys_added: list[str] = []
    out_parts: list[str] = []
    cursor = 0

    for m in list(open_re.finditer(src)):
        if m.start() < cursor:
            # This match is inside the inner of a previous element we already
            # consumed. Skip — the next `finditer` call on the rewritten src
            # would catch it, but we do a single pass here.
            continue

        attrs = m.group(1) or ""
        # Self-closing or void — nothing to translate.
        if attrs.rstrip().endswith("/"):
            continue
        # Already tagged for i18n.
        if _has_i18n_attr(attrs):
            continue

        close_at = _find_matching_close(src, tag, m.end())
        if close_at is None:
            continue

        inner = src[m.end() : close_at]
        stripped_inner = inner.strip()
        if not stripped_inner:
            continue

        has_child = _contains_inline_html(inner)
        if has_child and tag in HTML_TAGS:
            # Mixed-content element. Use data-i18n-html with the normalized
            # innerHTML as the key.
            key = _normalize(inner)
            # Skip if the key is dominated by a URL / file path (not a
            # natural-language sentence), or clearly contains JS we picked up
            # from an unmasked script block.
            if _has_code_markers(key):
                continue
            if not _is_translatable(re.sub(r"<[^>]+>", "", inner)):
                continue
            new_open = _insert_attr(m.group(0), "data-i18n-html")
            out_parts.append(src[cursor : m.start()])
            out_parts.append(new_open)
            cursor = m.end()
            catalog.setdefault(key, key)
            html_keys_added.append(key)
        elif has_child:
            # Not in HTML_TAGS whitelist — skip.
            continue
        else:
            key = _normalize(inner)
            if not _is_translatable(key) or _has_code_markers(key):
                continue
            new_open = _insert_attr(m.group(0), "data-i18n")
            out_parts.append(src[cursor : m.start()])
            out_parts.append(new_open)
            cursor = m.end()
            catalog.setdefault(key, key)
            keys_added.append(key)

    out_parts.append(src[cursor:])
    return "".join(out_parts), keys_added, html_keys_added


def _load_catalog() -> dict[str, str]:
    if CATALOG_PATH.exists():
        data = json.loads(CATALOG_PATH.read_text())
        # Filter to only the keys we preserve — values are always English.
        return {k: (v if isinstance(v, str) else k) for k, v in data.items()}
    return {}


def _save_catalog(catalog: dict[str, str]) -> None:
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Deterministic ordering by key so diffs stay small.
    ordered = dict(sorted(catalog.items()))
    CATALOG_PATH.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n")


# Pick up `t('…')` / `t("…")` calls from hand-written JS. This is how
# dynamically-rendered strings (nav labels, tooltips, inline-rendered cards)
# land in the catalog without us having to maintain two sources of truth.
# Match single or double quotes; backslash-escaped quotes inside the string
# are supported.
_T_CALL_RE = re.compile(
    r"""\bt\(\s*                 # t(
        (['"])                   # opening quote (group 1)
        ((?:\\.|(?!\1).)*)       # string body — escape-aware (group 2)
        \1                       # matching closing quote
        \s*[\),]""",  # closing ) or argument separator
    re.VERBOSE | re.DOTALL,
)


def _extract_js_strings(js_files: list[Path], catalog: dict[str, str]) -> int:
    added = 0
    for path in js_files:
        src = path.read_text()
        for m in _T_CALL_RE.finditer(src):
            quote, body = m.group(1), m.group(2)
            # Un-escape the few things that actually get escaped in JS
            # literals — the newline and the matching quote.
            raw = (
                body.replace("\\" + quote, quote)
                .replace("\\n", "\n")
                .replace("\\t", "\t")
            )
            key = _normalize(raw)
            if not _is_translatable(key):
                continue
            if key not in catalog:
                catalog[key] = key
                added += 1
    return added


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Don't write files.")
    ap.add_argument(
        "--pages",
        type=Path,
        default=PAGES,
        help="Directory with HTML files to rewrite.",
    )
    ap.add_argument(
        "--js",
        type=Path,
        default=STATIC,
        help="Directory with JS files to scan for t('…') calls.",
    )
    args = ap.parse_args()

    catalog = _load_catalog()
    pre_count = len(catalog)

    rewrites: list[Rewrite] = []
    for path in sorted(args.pages.glob("*.html")):
        rw = _rewrite_file(path, catalog)
        rewrites.append(rw)

    # Report HTML
    for rw in rewrites:
        added = len(rw.keys_added) + len(rw.html_keys_added)
        if added == 0 and rw.original == rw.updated:
            print(f"  {rw.path.name}: no changes")
            continue
        print(
            f"  {rw.path.name}: +{len(rw.keys_added)} text, "
            f"+{len(rw.html_keys_added)} html"
        )
        if not args.dry_run and rw.original != rw.updated:
            rw.path.write_text(rw.updated)

    # Also sweep JS files for t('…') calls.
    js_files = [p for p in sorted(args.js.glob("*.js")) if p.name != "i18n.js"]
    js_added = _extract_js_strings(js_files, catalog)
    print(f"  [js] scanned {len(js_files)} files, +{js_added} keys")

    # And inline <script> blocks inside HTML pages — a lot of dynamic UI
    # lives there, and once we've started wrapping those strings in t(…)
    # they belong in the catalog too.
    inline_added = _extract_js_strings(sorted(args.pages.glob("*.html")), catalog)
    print(f"  [html/inline-js] +{inline_added} keys")

    if not args.dry_run:
        _save_catalog(catalog)
    print(
        f"\nCatalog entries: {pre_count} → {len(catalog)} (+{len(catalog) - pre_count})"
    )
    print(
        f"Written to: {CATALOG_PATH.relative_to(ROOT)}"
        if not args.dry_run
        else "(dry-run)"
    )


if __name__ == "__main__":
    main()
