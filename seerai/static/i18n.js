/**
 * Tiny English-as-key i18n runtime.
 *
 * Loads /static/i18n/{lang}.json, exposes window.t(str) and
 * window.seerai.applyI18n(rootEl) for translating DOM after dynamic
 * rendering. Language choice lives in localStorage.seerai_lang (or the
 * browser default if unset); the UI toggle is rendered by nav.js.
 *
 * HTML elements opt in via either:
 *   <tag data-i18n>English text</tag>   -- replaces textContent
 *   <tag data-i18n-html>Text with <em>HTML</em></tag>  -- replaces innerHTML
 *   <tag data-i18n-attrs="title:Tooltip,placeholder:Search">…</tag>
 *     -- translates each "attr:English value" pair
 *
 * Catalog keys ARE the English strings. If a key isn't in the bundle,
 * we return it unchanged, so adding support is incremental.
 */
(function () {
    var LANG_KEY = 'seerai_lang';
    var USER_KEY = 'seerai_user';
    var DEFAULT = 'en';
    var SUPPORTED = ['en', 'de', 'it', 'ru'];

    // Install the lang + caller header injector as early as possible — i18n.js
    // is loaded synchronously at the top of every page, while nav.js is
    // deferred, so inline scripts that fetch during HTML parsing (e.g.
    // org_index resolving the viewer's root org) need the interceptor here.
    var _origFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
        try {
            init = init || {};
            var headers = new Headers(init.headers || (input && input.headers) || {});
            var storedLang = localStorage.getItem(LANG_KEY);
            if (storedLang && SUPPORTED.indexOf(storedLang) >= 0 && !headers.has('X-Seerai-Lang')) {
                headers.set('X-Seerai-Lang', storedLang);
            }
            var user = JSON.parse(localStorage.getItem(USER_KEY) || 'null');
            if (user && user.user_id && !headers.has('X-Caller-User-Id')) {
                headers.set('X-Caller-User-Id', user.user_id);
            }
            init.headers = headers;
        } catch (e) { /* best effort */ }
        return _origFetch(input, init);
    };

    var bundle = {};
    var lang = DEFAULT;

    function pickLang() {
        var stored = localStorage.getItem(LANG_KEY);
        if (stored && SUPPORTED.indexOf(stored) >= 0) return stored;
        var nav = (navigator.language || navigator.userLanguage || 'en').toLowerCase().slice(0, 2);
        return SUPPORTED.indexOf(nav) >= 0 ? nav : DEFAULT;
    }

    function normKey(s) {
        // Collapse internal whitespace so multi-line HTML text still matches
        // the flat key in the catalog.
        return String(s).replace(/\s+/g, ' ').trim();
    }

    function t(s) {
        if (s == null) return '';
        var key = normKey(s);
        if (!key) return s;
        return bundle[key] || s;
    }

    function translateTextContent(el) {
        var key = normKey(el.textContent);
        if (!key) return;
        var out = bundle[key];
        if (out && out !== key) el.textContent = out;
    }

    function translateInnerHtml(el) {
        // data-i18n-html: the attribute value (if set) wins over the current
        // innerHTML — that way the "source" is stable even after the runtime
        // has already rewritten the node once.
        var key = el.getAttribute('data-i18n-html');
        if (!key) {
            key = normKey(el.innerHTML);
            el.setAttribute('data-i18n-html', key);
        }
        var out = bundle[key];
        if (out && out !== key) el.innerHTML = out;
    }

    function translateAttrs(el) {
        var spec = el.getAttribute('data-i18n-attrs');
        if (!spec) return;
        // "title:English,placeholder:Search here"
        spec.split(',').forEach(function (pair) {
            var idx = pair.indexOf(':');
            if (idx < 0) return;
            var attr = pair.slice(0, idx).trim();
            var src = pair.slice(idx + 1).trim();
            if (!attr || !src) return;
            var out = bundle[src];
            if (out && out !== src) el.setAttribute(attr, out);
        });
    }

    function applyI18n(root) {
        root = root || document;
        if (lang === DEFAULT) {
            // Still process data-i18n-attrs — the attribute value is the key
            // so we only actually replace when a translation differs. No-op
            // for en, handled by the early return in translateAttrs.
        }
        root.querySelectorAll('[data-i18n]').forEach(translateTextContent);
        root.querySelectorAll('[data-i18n-html]').forEach(translateInnerHtml);
        root.querySelectorAll('[data-i18n-attrs]').forEach(translateAttrs);
    }

    function setLang(next) {
        if (SUPPORTED.indexOf(next) < 0) next = DEFAULT;
        localStorage.setItem(LANG_KEY, next);
        // Full reload is the right call here: dynamically-rendered pages
        // build HTML via t() at render time, and partial re-translation
        // would miss strings that were hard-coded in JS template literals.
        window.location.reload();
    }

    function loadBundle() {
        if (lang === DEFAULT) return Promise.resolve({});
        // Default browser caching is fine — FastAPI's StaticFiles sets ETag
        // headers, so the browser revalidates cheaply without serving a
        // stale bundle after we re-translate.
        return fetch('/static/i18n/' + lang + '.json')
            .then(function (r) { return r.ok ? r.json() : {}; })
            .catch(function () { return {}; });
    }

    // Fire off the bundle load ASAP so it's (hopefully) ready before pages
    // start calling t(). Pages that must guarantee translations are loaded
    // before rendering can await window.seerai.i18nReady.
    lang = pickLang();
    document.documentElement.lang = lang;
    var ready = loadBundle().then(function (b) {
        bundle = b || {};
        // Apply to whatever is already in the DOM at load time. Pages that
        // render dynamically must call window.seerai.applyI18n(root) themselves.
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function () { applyI18n(); });
        } else {
            applyI18n();
        }
        return bundle;
    });

    window.seerai = window.seerai || {};
    window.seerai.t = t;
    window.seerai.applyI18n = applyI18n;
    window.seerai.i18nReady = ready;
    window.seerai.getLang = function () { return lang; };
    window.seerai.setLang = setLang;
    window.seerai.supportedLangs = SUPPORTED;
    // Short global alias; most page templates use t('…') in JS.
    window.t = t;

    // Locale-aware formatters so number/date formatting follows the
    // active language without each page having to hard-code 'en-US'.
    window.seerai.fmtDate = function (iso, opts) {
        opts = opts || { month: 'short', day: 'numeric', year: 'numeric' };
        try {
            return new Date(iso).toLocaleDateString(lang, opts);
        } catch (e) {
            return new Date(iso).toLocaleDateString(undefined, opts);
        }
    };
    window.seerai.fmtNum = function (n, opts) {
        try { return Number(n).toLocaleString(lang, opts || {}); }
        catch (e) { return Number(n).toLocaleString(undefined, opts || {}); }
    };
})();
