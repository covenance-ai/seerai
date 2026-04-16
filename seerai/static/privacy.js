/**
 * Client-side privacy hider — reads window.seerai.privacyContext and hides
 * DOM nodes flagged with data-privacy-class that the viewer can't see.
 *
 * This is cosmetic: the server already returns the correct data (or 403s).
 * The hider prevents "flicker-on-hide" where a section briefly renders
 * before the XHR fails.
 *
 * Flags (on any element, re-evaluated whenever nav.js reports context or
 * the DOM mutates):
 *   data-privacy-class="individual"
 *     Hide unless privacy is OFF in the viewer's root org OR the viewer is
 *     the subject of this surface. Optional data-subject-user-id lets the
 *     element declare its subject (falls back to URL /sessions/{uid}/...).
 *   data-privacy-class="aggregate"
 *     Leave visible, but replace numeric cells inside
 *     [data-suppress-below="{min_cohort}"] rows with "suppressed".
 *   data-privacy-class="insight"
 *     Drop if data-kind is in the personal-insight-kinds set AND
 *     data-org-id belongs to a privacy-on root. (Usually insights are
 *     filtered server-side; this is a safety net for client-rendered cards.)
 */
(function () {
    'use strict';

    var ctx = null;

    // --- Set/update context (called by nav.js) ---
    window.seerai = window.seerai || {};
    window.seerai.applyPrivacy = function (newCtx) {
        ctx = newCtx;
        run();
    };

    function subjectFromElementOrURL(el) {
        var explicit = el.getAttribute('data-subject-user-id');
        if (explicit) return explicit;
        var m = window.location.pathname.match(/\/(?:sessions|session|my)\/([^\/]+)/);
        return m ? decodeURIComponent(m[1]) : null;
    }

    function hide(el) {
        el.style.display = 'none';
        el.setAttribute('aria-hidden', 'true');
    }

    function suppressRow(el) {
        // Replace text content of numeric cells with "—" and mark with class.
        if (el.dataset.privacySuppressed === '1') return;
        el.dataset.privacySuppressed = '1';
        el.classList.add('privacy-suppressed');
        var cells = el.querySelectorAll('[data-metric]');
        cells.forEach(function (c) { c.textContent = '—'; });
        // Add a visible marker if none present.
        if (!el.querySelector('.privacy-suppress-label')) {
            var span = document.createElement('span');
            span.className = 'privacy-suppress-label text-xs text-gray-400 italic ml-2';
            span.textContent = '(suppressed: too few members)';
            el.appendChild(span);
        }
    }

    function run() {
        if (!ctx) return;
        var personal = new Set(ctx.personal_insight_kinds || []);
        var minCohort = ctx.min_cohort_size || 3;
        var priv = !!ctx.privacy_mode;

        // INDIVIDUAL — hide unless privacy off OR viewer is subject.
        document.querySelectorAll('[data-privacy-class="individual"]').forEach(function (el) {
            if (!priv) return; // visible when privacy off for viewer's org
            var subj = subjectFromElementOrURL(el);
            if (subj && ctx.viewer_user_id && subj === ctx.viewer_user_id) return;
            hide(el);
        });

        // AGGREGATE — suppress rows that explicitly declare cohort size.
        document.querySelectorAll('[data-privacy-class="aggregate"]').forEach(function (el) {
            if (!priv) return;
            el.querySelectorAll('[data-user-count]').forEach(function (row) {
                var n = parseInt(row.getAttribute('data-user-count'), 10) || 0;
                if (n < minCohort) suppressRow(row);
            });
        });

        // INSIGHT — safety net for client-rendered cards.
        document.querySelectorAll('[data-privacy-class="insight"]').forEach(function (el) {
            var kind = el.getAttribute('data-kind');
            var orgId = el.getAttribute('data-org-id') || '';
            if (kind && personal.has(kind) && orgId && ctx.any_privacy_on) {
                // Per the server rule, only hide if the insight's root is priv-on.
                // The template can pre-compute that and set data-root-privacy="1".
                if (el.getAttribute('data-root-privacy') === '1') hide(el);
            }
        });
    }

    // Re-run whenever the DOM changes — dashboards render content async.
    var mo = new MutationObserver(function () { run(); });
    mo.observe(document.documentElement, { childList: true, subtree: true });

    // If context was set before this script loaded, apply now.
    if (window.seerai && window.seerai._pendingPrivacyContext) {
        window.seerai.applyPrivacy(window.seerai._pendingPrivacyContext);
    }
})();
