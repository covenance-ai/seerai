/**
 * Guided demo tour. Renders a right-hand panel that walks a viewer through
 * seerai's canonical feature path and tells them why each surface matters.
 *
 * State model (localStorage key `seerai_tour`):
 *   { version, enabled, dismissed, maxUnlocked, completed: [hrefs] }
 *
 * The panel's "current step" is derived from the URL — whatever route the user
 * is looking at is the step they're reading narrative about. `maxUnlocked` is
 * how far they've advanced; nav links past that index render locked.
 *
 * Steps vary by role:
 *   exec  → 8 stops covering every org surface
 *   user  → 3 stops (welcome, my sessions, done)
 *   admin → no tour (they have a separate support flow)
 *
 * Integration: nav.js asks window.seerai.tour.isUnlocked(href) when rendering;
 * tour calls window.seerai.renderSidebar() whenever state changes so locks
 * stay in sync without a full reload.
 */
(function () {
    var TOUR_KEY = 'seerai_tour';
    var FLOW_VERSION = 1;  // bump when the step list changes materially

    function t(s) { return (window.t ? window.t(s) : s); }
    function esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

    function currentUser() {
        try { return JSON.parse(localStorage.getItem('seerai_user')); } catch (e) { return null; }
    }

    // --- Step definitions ---
    function getSteps(user) {
        if (!user) return [];
        if (user.role === 'admin') return [];
        var uid = encodeURIComponent(user.user_id);

        if (user.role !== 'exec') {
            return [
                {
                    id: 'welcome', label: t('Welcome'), href: null,
                    why: t("seerai observes your AI conversations so your company can coach, learn from, and measure value created with AI — without the raw text leaving your control."),
                    how: t("We'll make two quick stops. Use Continue when you're ready."),
                },
                {
                    id: 'my-sessions', label: t('My Sessions'), href: '/my/' + uid,
                    why: t("Every chat you have with ChatGPT, Claude, or Gemini shows up here. If your org has privacy on, admins never see the raw text — only aggregates."),
                    how: t("Scan the list, then click any session to drill into the conversation."),
                },
                {
                    id: 'done', label: t('All set'), href: null,
                    why: t("That's the user-side view. Your admins see aggregated insights across the team."),
                    how: t("Explore freely. You can restart this tour any time from the right-hand pill."),
                },
            ];
        }

        return [
            {
                id: 'welcome', label: t('Welcome'), href: null,
                why: t("seerai turns your team's AI chats into measurable business value. This quick tour walks through every surface and tells you what it's worth."),
                how: t("Use Continue to unlock each feature in order — think of it as a guided first run."),
            },
            {
                id: 'dashboard', label: t('Dashboard'), href: '/exec',
                why: t("Your organization at a glance: who's using AI, how fast adoption is moving, and where risk is concentrated. The first thing execs open each morning."),
                how: t("Start here every day. Click into any team card to drill down."),
            },
            {
                id: 'analytics', label: t('Analytics'), href: '/exec/analytics',
                why: t("Usage trends that justify the spend. Seats activated, turns per user, adoption by role and department — compared across weeks."),
                how: t("Watch for adoption stalls. A flat line in a team is a signal to follow up with that manager."),
            },
            {
                id: 'insights', label: t('Insights'), href: '/exec/insights',
                why: t("Cross-team signals your managers wouldn't surface on their own: paygrade alignment, negative patterns, shared interests across departments."),
                how: t("Skim the top cards weekly. Each one is a conversation starter for a 1:1."),
            },
            {
                id: 'coach', label: t('Coach'), href: '/exec/coach',
                why: t("AI Coach nudges your team toward better prompting — factuality, efficiency, source hygiene — inside the chat, in real time."),
                how: t("Check acceptance rate and the estimated-value delta to see coaching ROI in dollars."),
            },
            {
                id: 'costs', label: t('Costs & ROI'), href: '/exec/costs',
                why: t("The spend side: subscription cost vs. estimated value captured, broken down by team. This is what you bring to the quarterly review."),
                how: t("Filter by team to find which ones pay for themselves and which need coaching to catch up."),
            },
            {
                id: 'privacy', label: t('Privacy'), href: '/admin/privacy',
                why: t("GDPR-ready controls. Flip privacy on and individual text is hidden from admins — only aggregates remain visible, with configurable cohort minimums."),
                how: t("Set the posture your DPO is comfortable with. The viewer's role determines what they can see."),
            },
            {
                id: 'done', label: t('All set'), href: null,
                why: t("That's the full surface. The demo uses a realistic snapshot — every chart, insight, and intervention is computed from actual conversations."),
                how: t("Explore freely. You can restart the tour any time from the right-hand pill."),
            },
        ];
    }

    // --- State ---
    function loadState() {
        try {
            var s = JSON.parse(localStorage.getItem(TOUR_KEY));
            if (!s || s.version !== FLOW_VERSION) return null;
            return s;
        } catch (e) { return null; }
    }
    function saveState(s) {
        s.version = FLOW_VERSION;
        localStorage.setItem(TOUR_KEY, JSON.stringify(s));
    }

    function defaultState() {
        return {
            version: FLOW_VERSION, enabled: true, dismissed: false,
            currentStep: 0, maxUnlocked: 0, completed: [],
        };
    }

    // Find the step index matching the current URL (exact path match).
    function urlStepIdx(steps) {
        var path = window.location.pathname;
        for (var i = 0; i < steps.length; i++) {
            if (steps[i].href === path) return i;
        }
        return -1;
    }

    // Step the panel should display. We track `currentStep` explicitly because
    // terminal steps (like "All set") have no href — the URL alone can't tell
    // us whether the user advanced to them. URL match still wins when the
    // user navigates via the sidebar to a previous feature (so the panel
    // repaints the matching narrative).
    function displayStepIdx(state, steps) {
        var max = steps.length - 1;
        var cs = typeof state.currentStep === 'number'
            ? Math.max(0, Math.min(state.currentStep, max))
            : 0;
        var u = urlStepIdx(steps);
        if (u >= 0 && steps[cs] && steps[cs].href !== null && u !== cs) {
            // User clicked a sidebar link for a feature they already unlocked —
            // show that step's narrative. (But don't override a no-href
            // terminal step: there, the URL doesn't represent the step.)
            return u;
        }
        return cs;
    }

    // --- Public API ---
    window.seerai = window.seerai || {};
    window.seerai.tour = {
        isActive: function () {
            var s = loadState();
            return !!(s && s.enabled && !s.dismissed);
        },

        // nav.js calls this for every nav item. Returns true when locking is
        // off (tour disabled / admin / href not part of tour) — only steps
        // above maxUnlocked are locked. The current URL is always considered
        // unlocked so the user never sees a lock on the page they're on.
        isUnlocked: function (href) {
            var s = loadState();
            if (!s || !s.enabled || s.dismissed) return true;
            if (href === window.location.pathname) return true;
            var steps = getSteps(currentUser());
            if (!steps.length) return true;
            var idx = -1;
            for (var i = 0; i < steps.length; i++) {
                if (steps[i].href === href) { idx = i; break; }
            }
            if (idx < 0) return true;  // not part of tour → always accessible
            return idx <= s.maxUnlocked;
        },

        // The href (or null) of the step the panel is currently on. nav.js
        // uses this to paint a spotlight ring on the matching sidebar item.
        currentHref: function () {
            var s = loadState();
            if (!s || !s.enabled || s.dismissed) return null;
            var steps = getSteps(currentUser());
            if (!steps.length) return null;
            var idx = displayStepIdx(s, steps);
            return steps[idx] ? (steps[idx].href || null) : null;
        },

        start: function () {
            var s = loadState() || defaultState();
            s.enabled = true;
            s.dismissed = false;
            if (typeof s.currentStep !== 'number') s.currentStep = 0;
            if (typeof s.maxUnlocked !== 'number') s.maxUnlocked = 0;
            if (!s.completed) s.completed = [];
            saveState(s);
            refreshNav();
            render();
        },

        dismiss: function () {
            var s = loadState() || defaultState();
            s.dismissed = true;
            saveState(s);
            document.body.classList.remove('seerai-tour-open');
            refreshNav();
            render();
        },

        reset: function () {
            localStorage.removeItem(TOUR_KEY);
            this.start();
        },

        next: function () {
            var s = loadState() || defaultState();
            var steps = getSteps(currentUser());
            if (!steps.length) return;
            var cur = displayStepIdx(s, steps);
            var nextIdx = Math.min(cur + 1, steps.length - 1);
            s.currentStep = nextIdx;
            if (nextIdx > s.maxUnlocked) s.maxUnlocked = nextIdx;
            saveState(s);
            var target = steps[nextIdx];
            if (target.href && window.location.pathname !== target.href) {
                window.location.href = target.href;
            } else {
                refreshNav();
                render();
            }
        },

        prev: function () {
            var s = loadState() || defaultState();
            var steps = getSteps(currentUser());
            if (!steps.length) return;
            var cur = displayStepIdx(s, steps);
            var prevIdx = Math.max(cur - 1, 0);
            s.currentStep = prevIdx;
            saveState(s);
            var target = steps[prevIdx];
            if (target.href && window.location.pathname !== target.href) {
                window.location.href = target.href;
            } else {
                refreshNav();
                render();
            }
        },

        goto: function (i) {
            var s = loadState() || defaultState();
            var steps = getSteps(currentUser());
            if (i < 0 || i >= steps.length) return;
            if (i > s.maxUnlocked) return;  // locked
            s.currentStep = i;
            saveState(s);
            var target = steps[i];
            if (target.href && window.location.pathname !== target.href) {
                window.location.href = target.href;
            } else {
                refreshNav();
                render();
            }
        },
    };

    // --- Styles ---
    var css =
        '#seerai-tour-panel{position:fixed;right:0;top:0;bottom:0;width:340px;z-index:45;' +
        'background:#fff;border-left:1px solid #e5e7eb;display:flex;flex-direction:column;' +
        'font-size:.875rem;color:#1f2937;transition:transform 220ms cubic-bezier(.4,0,.2,1)}' +
        '.dark #seerai-tour-panel{background:#0b1220;border-left-color:#1f2937;color:#e5e7eb}' +
        '#seerai-tour-panel.tour-hidden{display:none}' +
        'body.seerai-tour-open{padding-right:340px;transition:padding-right 220ms cubic-bezier(.4,0,.2,1)}' +
        '#seerai-tour-reopen{position:fixed;right:0;top:96px;z-index:44;' +
        'background:#2563eb;color:#fff;border:none;border-radius:10px 0 0 10px;' +
        'padding:10px 14px 10px 12px;cursor:pointer;box-shadow:-4px 4px 16px rgba(0,0,0,.18);' +
        'display:none;align-items:center;gap:8px;font-size:.75rem;font-weight:600;letter-spacing:.02em}' +
        '#seerai-tour-reopen:hover{background:#1d4ed8}' +
        '#seerai-tour-panel .tour-header{padding:14px 16px;border-bottom:1px solid #e5e7eb;' +
        'display:flex;align-items:center;justify-content:space-between;gap:8px;flex-shrink:0}' +
        '.dark #seerai-tour-panel .tour-header{border-bottom-color:#1f2937}' +
        '#seerai-tour-panel .tour-title{font-size:.7rem;font-weight:700;text-transform:uppercase;' +
        'letter-spacing:.1em;color:#2563eb}' +
        '.dark #seerai-tour-panel .tour-title{color:#60a5fa}' +
        '#seerai-tour-panel .tour-sub{font-size:.7rem;color:#6b7280;margin-top:2px}' +
        '.dark #seerai-tour-panel .tour-sub{color:#9ca3af}' +
        '#seerai-tour-panel .tour-close{background:none;border:none;color:#9ca3af;cursor:pointer;' +
        'padding:2px 8px;font-size:1.25rem;line-height:1;border-radius:6px}' +
        '#seerai-tour-panel .tour-close:hover{background:#f3f4f6;color:#111827}' +
        '.dark #seerai-tour-panel .tour-close:hover{background:#1f2937;color:#f3f4f6}' +
        '#seerai-tour-panel .tour-steps{padding:10px 10px 6px;overflow-y:auto;flex-shrink:0;' +
        'max-height:38%;border-bottom:1px solid #e5e7eb}' +
        '.dark #seerai-tour-panel .tour-steps{border-bottom-color:#1f2937}' +
        '#seerai-tour-panel .tour-step{display:flex;align-items:center;gap:10px;padding:7px 10px;' +
        'border-radius:8px;cursor:pointer;margin-bottom:2px;font-size:.8rem;line-height:1.2;' +
        'color:#374151;transition:background 120ms}' +
        '.dark #seerai-tour-panel .tour-step{color:#d1d5db}' +
        '#seerai-tour-panel .tour-step:hover{background:#f3f4f6}' +
        '.dark #seerai-tour-panel .tour-step:hover{background:#1f2937}' +
        '#seerai-tour-panel .tour-step.active{background:#eff6ff;color:#1d4ed8;font-weight:600}' +
        '.dark #seerai-tour-panel .tour-step.active{background:rgba(30,58,138,.35);color:#93c5fd}' +
        '#seerai-tour-panel .tour-step.locked{color:#9ca3af;cursor:not-allowed;opacity:.7}' +
        '.dark #seerai-tour-panel .tour-step.locked{color:#6b7280}' +
        '#seerai-tour-panel .tour-step.locked:hover{background:transparent}' +
        '#seerai-tour-panel .tour-marker{width:22px;height:22px;border-radius:50%;' +
        'display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;' +
        'font-size:.68rem;font-weight:700;background:#e5e7eb;color:#6b7280}' +
        '.dark #seerai-tour-panel .tour-marker{background:#1f2937;color:#9ca3af}' +
        '#seerai-tour-panel .tour-step.active .tour-marker{background:#3b82f6;color:#fff}' +
        '#seerai-tour-panel .tour-step.done .tour-marker{background:#10b981;color:#fff}' +
        '#seerai-tour-panel .tour-body{padding:18px 18px 14px;overflow-y:auto;flex:1;min-height:0}' +
        '#seerai-tour-panel .tour-kicker{font-size:.65rem;text-transform:uppercase;letter-spacing:.1em;' +
        'color:#9ca3af;font-weight:600;margin-bottom:6px}' +
        '#seerai-tour-panel .tour-heading{font-size:1.15rem;font-weight:700;color:#111827;' +
        'margin-bottom:14px;line-height:1.25;letter-spacing:-.01em}' +
        '.dark #seerai-tour-panel .tour-heading{color:#f3f4f6}' +
        '#seerai-tour-panel .tour-section{margin-bottom:14px}' +
        '#seerai-tour-panel .tour-section-title{font-size:.65rem;text-transform:uppercase;' +
        'letter-spacing:.1em;color:#6b7280;font-weight:700;margin-bottom:5px}' +
        '.dark #seerai-tour-panel .tour-section-title{color:#9ca3af}' +
        '#seerai-tour-panel .tour-section-body{color:#374151;line-height:1.55;font-size:.85rem}' +
        '.dark #seerai-tour-panel .tour-section-body{color:#cbd5e1}' +
        '#seerai-tour-panel .tour-actions{padding:12px 14px;border-top:1px solid #e5e7eb;' +
        'display:flex;align-items:center;justify-content:space-between;gap:8px;flex-shrink:0}' +
        '.dark #seerai-tour-panel .tour-actions{border-top-color:#1f2937}' +
        '#seerai-tour-panel .tour-btn{padding:8px 14px;border-radius:7px;font-size:.8rem;' +
        'font-weight:600;cursor:pointer;border:1px solid transparent;transition:background 120ms}' +
        '#seerai-tour-panel .tour-btn-primary{background:#2563eb;color:#fff}' +
        '#seerai-tour-panel .tour-btn-primary:hover{background:#1d4ed8}' +
        '#seerai-tour-panel .tour-btn-secondary{background:transparent;color:#6b7280;border-color:#e5e7eb}' +
        '.dark #seerai-tour-panel .tour-btn-secondary{color:#9ca3af;border-color:#374151}' +
        '#seerai-tour-panel .tour-btn-secondary:hover{background:#f3f4f6}' +
        '.dark #seerai-tour-panel .tour-btn-secondary:hover{background:#1f2937}' +
        '#seerai-tour-panel .tour-btn[disabled]{opacity:.35;cursor:not-allowed}' +
        // Narrow viewport: hide the panel entirely (it competes with the sidebar
        // and would overlap content on tablets). Reopen pill also hidden — the
        // tour is a desktop-first demo affordance.
        '@media(max-width:1279px){body.seerai-tour-open{padding-right:0}' +
        '#seerai-tour-panel,#seerai-tour-reopen{display:none !important}}' +
        // Locked nav items — applied by nav.js via the seerai-nav-locked class.
        '.seerai-nav-locked{opacity:.45;cursor:not-allowed !important;' +
        'pointer-events:none;position:relative}' +
        '.seerai-nav-locked:hover{background:transparent !important;color:inherit !important}' +
        '.seerai-nav-lock{margin-left:auto;font-size:.7rem;opacity:.7}' +
        // Spotlight on the sidebar item matching the tour's current step.
        // Uses an inset box-shadow ring so it layers cleanly over the existing
        // hover/active backgrounds without shifting layout.
        '.seerai-tour-target{position:relative;animation:seerai-tour-pulse 2s ease-in-out infinite}' +
        '.seerai-tour-target::after{content:"";position:absolute;inset:-2px;border-radius:10px;' +
        'pointer-events:none;box-shadow:0 0 0 2px #3b82f6, 0 0 14px rgba(59,130,246,.45);' +
        'animation:seerai-tour-glow 2s ease-in-out infinite}' +
        '@keyframes seerai-tour-pulse{' +
        '0%,100%{transform:scale(1)}50%{transform:scale(1.02)}}' +
        '@keyframes seerai-tour-glow{' +
        '0%,100%{opacity:.55}50%{opacity:1}}' +
        // When sidebar is collapsed, the label hides — keep the ring on the icon box.
        '#seerai-sidebar.collapsed .seerai-tour-target::after{inset:-1px}';
    var styleEl = document.createElement('style');
    styleEl.id = 'seerai-tour-style';
    styleEl.textContent = css;
    document.head.appendChild(styleEl);

    // --- DOM ---
    var panel, reopenBtn;
    function ensureDom() {
        if (panel) return;
        panel = document.createElement('aside');
        panel.id = 'seerai-tour-panel';
        panel.classList.add('tour-hidden');
        document.body.appendChild(panel);

        reopenBtn = document.createElement('button');
        reopenBtn.id = 'seerai-tour-reopen';
        reopenBtn.type = 'button';
        reopenBtn.innerHTML = '<span aria-hidden="true">◂</span><span>' + esc(t('Demo tour')) + '</span>';
        reopenBtn.addEventListener('click', function () { window.seerai.tour.start(); });
        document.body.appendChild(reopenBtn);
    }

    function refreshNav() {
        if (window.seerai && typeof window.seerai.renderSidebar === 'function') {
            try { window.seerai.renderSidebar(); } catch (e) { /* nav not ready yet */ }
        }
    }

    function render() {
        ensureDom();
        var user = currentUser();
        var steps = getSteps(user);
        var state = loadState();

        if (!state || !state.enabled || state.dismissed || !steps.length) {
            panel.classList.add('tour-hidden');
            document.body.classList.remove('seerai-tour-open');
            reopenBtn.style.display = (steps.length && state && state.dismissed) ? 'inline-flex' : 'none';
            return;
        }

        panel.classList.remove('tour-hidden');
        document.body.classList.add('seerai-tour-open');
        reopenBtn.style.display = 'none';

        var cur = displayStepIdx(state, steps);
        var step = steps[cur];

        var stepsHtml = '';
        for (var i = 0; i < steps.length; i++) {
            var st = steps[i];
            var cls = 'tour-step';
            var marker = String(i + 1);
            var done = i < state.maxUnlocked && i !== cur;
            var locked = i > state.maxUnlocked;
            if (i === cur) cls += ' active';
            else if (done) { cls += ' done'; marker = '✓'; }
            else if (locked) { cls += ' locked'; marker = '·'; }
            stepsHtml += '<div class="' + cls + '" data-step="' + i + '">'
                + '<span class="tour-marker">' + marker + '</span>'
                + '<span>' + esc(st.label) + '</span>'
                + '</div>';
        }

        var isLast = (cur === steps.length - 1);
        var nextLabel = isLast ? t('Finish tour') : t('Continue');
        var prevDisabled = cur === 0;

        panel.innerHTML =
            '<div class="tour-header">'
            + '<div>'
            + '<div class="tour-title">' + esc(t('Demo tour')) + '</div>'
            + '<div class="tour-sub">' + esc(t('Step')) + ' ' + (cur + 1) + ' / ' + steps.length + '</div>'
            + '</div>'
            + '<button class="tour-close" type="button" id="seerai-tour-close" aria-label="' + esc(t('Hide tour')) + '">×</button>'
            + '</div>'
            + '<div class="tour-steps">' + stepsHtml + '</div>'
            + '<div class="tour-body">'
            + '<div class="tour-kicker">' + esc(t('Now viewing')) + '</div>'
            + '<div class="tour-heading">' + esc(step.label) + '</div>'
            + '<div class="tour-section">'
            + '<div class="tour-section-title">' + esc(t('Why this matters')) + '</div>'
            + '<div class="tour-section-body">' + esc(step.why) + '</div>'
            + '</div>'
            + '<div class="tour-section">'
            + '<div class="tour-section-title">' + esc(t('How to use it')) + '</div>'
            + '<div class="tour-section-body">' + esc(step.how) + '</div>'
            + '</div>'
            + '</div>'
            + '<div class="tour-actions">'
            + '<button class="tour-btn tour-btn-secondary" type="button" id="seerai-tour-prev"'
            + (prevDisabled ? ' disabled' : '') + '>‹ ' + esc(t('Back')) + '</button>'
            + '<button class="tour-btn tour-btn-primary" type="button" id="seerai-tour-next">'
            + esc(nextLabel) + (isLast ? '' : ' ›') + '</button>'
            + '</div>';

        document.getElementById('seerai-tour-close').addEventListener('click', function () {
            window.seerai.tour.dismiss();
        });
        document.getElementById('seerai-tour-next').addEventListener('click', function () {
            if (isLast) window.seerai.tour.dismiss();
            else window.seerai.tour.next();
        });
        if (!prevDisabled) {
            document.getElementById('seerai-tour-prev').addEventListener('click', function () {
                window.seerai.tour.prev();
            });
        }
        panel.querySelectorAll('[data-step]').forEach(function (el) {
            el.addEventListener('click', function () {
                var i = parseInt(el.dataset.step, 10);
                window.seerai.tour.goto(i);
            });
        });
    }

    // Mark the current URL as visited, bumping maxUnlocked/completed. Runs on
    // every page load so direct deep-links (user typed /exec/coach) still
    // progress the tour instead of silently blocking them.
    function markVisit() {
        var s = loadState();
        if (!s || !s.enabled || s.dismissed) return;
        var steps = getSteps(currentUser());
        if (!steps.length) return;
        var idx = urlStepIdx(steps);
        if (idx < 0) return;
        var changed = false;
        if (idx > s.maxUnlocked) { s.maxUnlocked = idx; changed = true; }
        // Keep currentStep synced to the URL when the user clicks through the
        // sidebar — but never rewind past a no-href terminal step they
        // already reached (they might be on /my/uid viewing the "All set"
        // wrap-up; we don't want to drop them back onto My Sessions).
        var curStep = steps[s.currentStep || 0];
        var onTerminal = curStep && curStep.href === null && s.currentStep > idx;
        if (!onTerminal && idx !== s.currentStep) { s.currentStep = idx; changed = true; }
        var href = steps[idx].href;
        if (href && s.completed.indexOf(href) === -1) { s.completed.push(href); changed = true; }
        if (changed) saveState(s);
    }

    function init() {
        var user = currentUser();
        if (!user) return;  // user picker open; we re-init after they choose (full reload).
        var steps = getSteps(user);
        if (!steps.length) { render(); return; }

        // Auto-start on first ever visit. Skip markVisit on a brand-new tour so
        // the user sees Welcome first — they can click Continue to engage.
        var wasFresh = !loadState();
        if (wasFresh) saveState(defaultState());
        else markVisit();

        render();
        refreshNav();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
