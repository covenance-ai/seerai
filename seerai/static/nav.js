/**
 * Collapsible sidebar navigation with user switcher, theme toggle,
 * company-aware access control, and datasource selector.
 * Include via <script src="/static/nav.js"></script> in every page.
 * Requires Tailwind CDN loaded before this script.
 */
(function () {
    var USER_KEY = 'seerai_user';
    var THEME_KEY = 'seerai_theme';
    var SIDEBAR_KEY = 'seerai_sidebar';

    // --- Company branding ---
    var COMPANY_BRANDS = {
        'acme': { name: 'Acme Corp', color: '#3B82F6', initial: 'A' },
        'initech': { name: 'Initech', color: '#10B981', initial: 'I' },
    };

    var _companyMap = {};      // org_id -> root_org_id
    var _userCompanyMap = {};  // user_id -> root_org_id
    var _orgNames = {};        // org_id -> display name
    var _allUsers = [];
    var _dsInfo = null;

    // --- Public API ---
    window.seerai = window.seerai || {};
    window.seerai.COMPANY_BRANDS = COMPANY_BRANDS;

    window.seerai.companyBadge = function (rootOrgId, opts) {
        opts = opts || {};
        var brand = COMPANY_BRANDS[rootOrgId];
        if (!brand) return '';
        var sz = opts.size === 'lg' ? 'w-7 h-7 text-xs' : 'w-5 h-5 text-[0.6rem]';
        var nameHtml = opts.showName !== false
            ? '<span class="text-xs text-gray-500 dark:text-gray-400">' + brand.name + '</span>'
            : '';
        return '<span class="inline-flex items-center gap-1.5">'
            + '<span class="' + sz + ' rounded-full inline-flex items-center justify-center text-white font-bold shrink-0" style="background:' + brand.color + '">' + brand.initial + '</span>'
            + nameHtml + '</span>';
    };

    window.seerai.getUserCompany = function (userId) { return _userCompanyMap[userId] || null; };
    window.seerai.getCompany = function (orgId) { return _companyMap[orgId] || null; };
    window.seerai.getCurrentUser = getCurrentUser;

    window.seerai.canAccessUser = function (targetUserId) {
        var user = getCurrentUser();
        if (!user) return false;
        if (user.role === 'admin') return true;
        if (user.user_id === targetUserId) return true;
        var myCompany = user.company;
        var targetCompany = _userCompanyMap[targetUserId];
        return myCompany && targetCompany && myCompany === targetCompany;
    };

    // --- Data source ---
    function fetchDatasource() {
        return fetch('/api/datasource').then(function (r) { return r.json(); })
            .then(function (info) { _dsInfo = info; return info; });
    }

    function switchDatasource(source) {
        return fetch('/api/datasource', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source: source, local_available: false }),
        }).then(function (r) { return r.json(); })
            .then(function (info) { _dsInfo = info; return info; });
    }

    function downloadSnapshot() {
        return fetch('/api/datasource/download', { method: 'POST' }).then(function (r) { return r.json(); });
    }

    // --- Company data ---
    async function loadCompanyData() {
        var results = await Promise.all([
            fetch('/api/orgs').then(function (r) { return r.json(); }),
            fetch('/api/users').then(function (r) { return r.json(); }),
        ]);
        var roots = results[0];
        _allUsers = results[1];

        var trees = await Promise.all(
            roots.map(function (r) { return fetch('/api/orgs/' + encodeURIComponent(r.org_id) + '/tree').then(function (t) { return t.json(); }); })
        );

        function walk(node, rootId) {
            _companyMap[node.node.org_id] = rootId;
            _orgNames[node.node.org_id] = node.node.name;
            node.children.forEach(function (c) { walk(c, rootId); });
        }
        trees.forEach(function (t) { walk(t, t.node.org_id); });

        for (var i = 0; i < _allUsers.length; i++) {
            var u = _allUsers[i];
            if (u.org_id) _userCompanyMap[u.user_id] = _companyMap[u.org_id] || null;
        }
    }

    // --- Theme ---
    function getTheme() {
        return localStorage.getItem(THEME_KEY)
            || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    }

    function applyTheme(theme) {
        document.documentElement.classList.toggle('dark', theme === 'dark');
        localStorage.setItem(THEME_KEY, theme);
    }

    applyTheme(getTheme());

    // --- User ---
    function getCurrentUser() {
        try { return JSON.parse(localStorage.getItem(USER_KEY)); }
        catch (e) { return null; }
    }

    function setCurrentUser(user) {
        localStorage.setItem(USER_KEY, JSON.stringify(user));
    }

    function esc(s) {
        var d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    // --- Access control ---
    function checkPageAccess() {
        var user = getCurrentUser();
        if (!user) return;
        var path = window.location.pathname;
        var isAdmin = user.role === 'admin';

        if (path === '/') {
            if (!isAdmin) {
                window.location.replace(user.role === 'exec' ? '/exec' : '/my/' + encodeURIComponent(user.user_id));
            }
            return;
        }
        // /exec is exec-only
        if (path.startsWith('/exec') && !isAdmin && user.role !== 'exec') {
            window.location.replace('/my/' + encodeURIComponent(user.user_id));
            return;
        }
        // /sessions/{uid} (the user-listing page) is not for admin — admin
        // sees only flagged items via /. Execs can only view same-company users.
        if (path.match(/^\/sessions\//)) {
            if (isAdmin) {
                window.location.replace('/');
                return;
            }
            var parts = path.split('/');
            var targetId = decodeURIComponent(parts[2]);
            var targetCompany = _userCompanyMap[targetId];
            if (targetCompany && user.company && targetCompany !== user.company) {
                window.location.replace('/my/' + encodeURIComponent(user.user_id));
                return;
            }
        }
        // /session/{uid}/{sid} (single conversation) — admin can view ONLY if
        // that session is flagged for support; execs can view same-company.
        if (path.match(/^\/session\//)) {
            var sparts = path.split('/');
            var targetUid = decodeURIComponent(sparts[2]);
            var targetSid = decodeURIComponent(sparts[3] || '');
            if (isAdmin) {
                fetch('/api/users/' + encodeURIComponent(targetUid) + '/sessions/' + encodeURIComponent(targetSid))
                    .then(function (r) { return r.ok ? r.json() : null; })
                    .then(function (s) {
                        if (!s || !s.flagged_for_support_at) {
                            window.location.replace('/');
                        }
                    })
                    .catch(function () { window.location.replace('/'); });
                return;
            }
            var tc = _userCompanyMap[targetUid];
            if (tc && user.company && tc !== user.company) {
                window.location.replace('/my/' + encodeURIComponent(user.user_id));
            }
        }
    }

    // --- Sidebar state ---
    function sbExpanded() {
        return localStorage.getItem(SIDEBAR_KEY) !== 'collapsed';
    }

    function setSbExpanded(val) {
        localStorage.setItem(SIDEBAR_KEY, val ? 'expanded' : 'collapsed');
    }

    // --- Inject sidebar styles ---
    var styleEl = document.createElement('style');
    styleEl.textContent =
        '#seerai-sidebar{width:224px;transition:width 200ms cubic-bezier(.4,0,.2,1)}' +
        '#seerai-sidebar.collapsed{width:64px}' +
        '#seerai-sidebar .nav-label,#seerai-sidebar .section-label,#seerai-sidebar .user-info{' +
        'transition:opacity 150ms ease 40ms;white-space:nowrap;overflow:hidden}' +
        '#seerai-sidebar.collapsed .nav-label,#seerai-sidebar.collapsed .section-label,#seerai-sidebar.collapsed .user-info{' +
        'opacity:0;max-width:0;transition:opacity 80ms ease}' +
        'body.seerai-layout{padding-left:224px;transition:padding-left 200ms cubic-bezier(.4,0,.2,1)}' +
        'body.seerai-layout.sb-collapsed{padding-left:64px}' +
        '.nav-tip{position:absolute;left:calc(100% + 6px);top:50%;transform:translateY(-50%);' +
        'padding:4px 10px;border-radius:6px;font-size:.75rem;font-weight:500;' +
        'white-space:nowrap;pointer-events:none;opacity:0;transition:opacity 120ms ease;z-index:200}' +
        '#seerai-sidebar.collapsed .nav-item:hover .nav-tip{opacity:1}' +
        '#seerai-sidebar .nav-item.active::before{content:"";position:absolute;left:0;' +
        'top:6px;bottom:6px;width:3px;border-radius:0 4px 4px 0;background:#3b82f6}' +
        '#seerai-collapse-btn svg{transition:transform 200ms ease}' +
        '#seerai-sidebar.collapsed #seerai-collapse-btn svg{transform:rotate(180deg)}' +
        '#seerai-mobile-bar{display:none}#seerai-backdrop{display:none}' +
        '@media(max-width:1023px){' +
        '#seerai-sidebar{transform:translateX(-100%);' +
        'transition:transform 250ms cubic-bezier(.4,0,.2,1);width:272px!important;z-index:60}' +
        '#seerai-sidebar.collapsed{width:272px!important}' +
        '#seerai-sidebar.mobile-open{transform:translateX(0)}' +
        '#seerai-sidebar.mobile-open .nav-label,' +
        '#seerai-sidebar.mobile-open .section-label,' +
        '#seerai-sidebar.mobile-open .user-info{opacity:1!important;max-width:none!important}' +
        'body.seerai-layout,body.seerai-layout.sb-collapsed{padding-left:0!important;padding-top:48px}' +
        '#seerai-mobile-bar{display:flex}' +
        '#seerai-backdrop.visible{display:block}' +
        '#seerai-collapse-btn{display:none!important}' +
        '}';
    document.head.appendChild(styleEl);

    // --- SVG icons ---
    var ico = {
        chat: '<svg class="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>',
        grid: '<svg class="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25a2.25 2.25 0 01-2.25-2.25v-2.25z"/></svg>',
        chart: '<svg class="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.28m5.94 2.28l-2.28 5.941"/></svg>',
        users: '<svg class="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z"/></svg>',
        chevL: '<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5"/></svg>',
        sun: '<svg class="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z"/></svg>',
        moon: '<svg class="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z"/></svg>',
        db: '<svg class="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125"/></svg>',
        cloud: '<svg class="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M2.25 15a4.5 4.5 0 004.5 4.5H18a3.75 3.75 0 001.332-7.257 3 3 0 00-3.758-3.848 5.25 5.25 0 00-10.233 2.33A4.502 4.502 0 002.25 15z"/></svg>',
        menu: '<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"/></svg>',
        spark: '<svg class="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z"/></svg>',
        bars: '<svg class="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"/></svg>',
    };

    // --- Navigation definition ---
    function getNavSections() {
        var user = getCurrentUser();
        var isAdmin = user && user.role === 'admin';
        var isExec = user && user.role === 'exec';
        var path = window.location.pathname;
        var sections = [];

        if (isAdmin) {
            // Admin (seer.ai platform staff) only sees flagged items —
            // no global user list, dashboards, or insights.
            sections.push({
                label: 'Platform',
                items: [{
                    icon: ico.users, label: 'Support Review', href: '/',
                    active: path === '/' || path.startsWith('/session/'),
                }],
            });
        }

        if (user && !isAdmin) {
            sections.push({
                label: 'Personal',
                items: [{
                    icon: ico.chat, label: 'My Sessions',
                    href: '/my/' + encodeURIComponent(user.user_id),
                    active: path.startsWith('/my/'),
                }],
            });
        }

        if (isExec) {
            sections.push({
                label: 'Organization',
                items: [
                    {
                        icon: ico.grid, label: 'Dashboard', href: '/exec',
                        active: path.startsWith('/exec')
                            && !path.startsWith('/exec/costs')
                            && !path.startsWith('/exec/insights')
                            && !path.startsWith('/exec/analytics'),
                    },
                    {
                        icon: ico.bars, label: 'Analytics', href: '/exec/analytics',
                        active: path.startsWith('/exec/analytics'),
                    },
                    {
                        icon: ico.spark, label: 'Insights', href: '/exec/insights',
                        active: path.startsWith('/exec/insights'),
                    },
                    {
                        icon: ico.chart, label: 'Costs & ROI', href: '/exec/costs',
                        active: path.startsWith('/exec/costs'),
                    },
                ],
            });
        }

        return sections;
    }

    // --- Create DOM ---
    var sidebar = document.createElement('aside');
    sidebar.id = 'seerai-sidebar';
    sidebar.className = 'fixed left-0 top-0 bottom-0 z-50 flex flex-col border-r bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-800 overflow-hidden select-none';
    if (!sbExpanded()) sidebar.classList.add('collapsed');

    var mobileBar = document.createElement('div');
    mobileBar.id = 'seerai-mobile-bar';
    mobileBar.className = 'fixed top-0 left-0 right-0 z-40 h-12 items-center px-3 gap-3 border-b bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-800';

    var backdrop = document.createElement('div');
    backdrop.id = 'seerai-backdrop';
    backdrop.className = 'fixed inset-0 z-[55] bg-black/40';
    backdrop.addEventListener('click', closeMobile);

    document.body.prepend(backdrop);
    document.body.prepend(mobileBar);
    document.body.prepend(sidebar);
    document.body.classList.add('seerai-layout');
    if (!sbExpanded()) document.body.classList.add('sb-collapsed');

    // --- Render mobile bar ---
    function renderMobileBar() {
        mobileBar.innerHTML =
            '<button id="seerai-hamburger" class="p-1.5 -ml-1 rounded-lg text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">'
            + ico.menu + '</button>'
            + '<a href="/" class="flex items-center gap-2">'
            + '<div class="w-6 h-6 rounded-md bg-blue-600 flex items-center justify-center text-white font-bold text-xs shrink-0">s</div>'
            + '<span class="font-semibold text-gray-900 dark:text-white text-sm">seerai</span></a>';
        document.getElementById('seerai-hamburger').addEventListener('click', function () {
            sidebar.classList.add('mobile-open');
            backdrop.classList.add('visible');
        });
    }

    // --- Render sidebar ---
    function renderSidebar() {
        var user = getCurrentUser();
        var isDark = getTheme() === 'dark';
        var ds = _dsInfo;
        var sections = getNavSections();

        // Build nav items
        var navHtml = '';
        for (var si = 0; si < sections.length; si++) {
            var section = sections[si];
            navHtml += '<div class="' + (si > 0 ? 'mt-5' : '') + '">'
                + '<div class="section-label px-4 mb-1.5 text-[0.6rem] font-semibold uppercase tracking-widest text-gray-400 dark:text-gray-500">'
                + section.label + '</div>';
            for (var ii = 0; ii < section.items.length; ii++) {
                var item = section.items[ii];
                var act = item.active;
                var cls = act
                    ? 'bg-blue-50 dark:bg-blue-950/50 text-blue-700 dark:text-blue-300'
                    : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100/80 dark:hover:bg-gray-800/60 hover:text-gray-900 dark:hover:text-gray-200';
                navHtml += '<a href="' + item.href + '" class="nav-item ' + (act ? 'active' : '')
                    + ' relative flex items-center gap-3 mx-2 px-2.5 py-2 rounded-lg text-sm font-medium transition-colors ' + cls + '">'
                    + item.icon
                    + '<span class="nav-label">' + item.label + '</span>'
                    + '<span class="nav-tip bg-gray-800 dark:bg-gray-200 text-white dark:text-gray-900 shadow-lg">' + item.label + '</span>'
                    + '</a>';
            }
            navHtml += '</div>';
        }

        // User avatar
        var initials = user ? user.user_id.slice(0, 2).toUpperCase() : '?';
        var avatarBg = 'bg-gradient-to-br from-blue-400 to-indigo-500';
        var avatarStyle = '';
        if (user && user.company && COMPANY_BRANDS[user.company]) {
            avatarBg = '';
            avatarStyle = ' style="background:' + COMPANY_BRANDS[user.company].color + '"';
        }

        // Role badge
        var roleBadge = '';
        if (user) {
            if (user.role === 'admin') {
                roleBadge = '<span class="nav-label text-[0.55rem] ml-1 px-1 py-0.5 rounded font-semibold uppercase bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400">admin</span>';
            } else if (user.role === 'exec') {
                roleBadge = '<span class="nav-label text-[0.55rem] ml-1 px-1 py-0.5 rounded font-semibold uppercase bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">exec</span>';
            }
        }

        // Datasource
        var dsLabel = ds ? ds.source : '...';
        var dsIcon = dsLabel === 'local' ? ico.db : ico.cloud;
        var dsDot = dsLabel === 'local' ? 'bg-blue-400' : 'bg-emerald-400';
        var dsText = dsLabel === 'local' ? 'Local data' : 'Firestore';

        // User subtitle
        var userSub = 'Click to choose';
        if (user) {
            if (user.company && COMPANY_BRANDS[user.company]) {
                userSub = COMPANY_BRANDS[user.company].name;
            } else if (user.org_id) {
                userSub = _orgNames[user.org_id] || user.org_id;
            }
        }

        sidebar.innerHTML =
            // Logo
            '<div class="flex items-center h-14 px-4 shrink-0">'
            + '<a href="/" class="flex items-center gap-2.5 text-gray-900 dark:text-white">'
            + '<div class="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-sm shrink-0">s</div>'
            + '<span class="nav-label font-semibold text-base tracking-tight">seerai</span>'
            + '</a></div>'

            + '<div class="h-px mx-3 bg-gray-100 dark:bg-gray-800 shrink-0"></div>'

            // Nav
            + '<nav class="flex-1 overflow-y-auto py-3 px-1">' + navHtml + '</nav>'

            + '<div class="h-px mx-3 bg-gray-100 dark:bg-gray-800 shrink-0"></div>'

            // Bottom controls
            + '<div class="p-2 space-y-0.5 shrink-0">'
            // Datasource
            + '<button id="seerai-ds-btn" class="nav-item relative w-full flex items-center gap-3 px-2.5 py-2 rounded-lg text-sm transition-colors text-gray-500 dark:text-gray-400 hover:bg-gray-100/80 dark:hover:bg-gray-800/60 hover:text-gray-900 dark:hover:text-gray-200 cursor-pointer">'
            + '<div class="relative shrink-0">' + dsIcon + '<span class="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full ' + dsDot + ' ring-2 ring-white dark:ring-gray-900"></span></div>'
            + '<span class="nav-label text-xs font-medium">' + dsText + '</span>'
            + '<span class="nav-tip bg-gray-800 dark:bg-gray-200 text-white dark:text-gray-900 shadow-lg">' + dsText + '</span>'
            + '</button>'
            // Theme
            + '<button id="seerai-theme-btn" class="nav-item relative w-full flex items-center gap-3 px-2.5 py-2 rounded-lg text-sm transition-colors text-gray-500 dark:text-gray-400 hover:bg-gray-100/80 dark:hover:bg-gray-800/60 hover:text-gray-900 dark:hover:text-gray-200 cursor-pointer">'
            + (isDark ? ico.sun : ico.moon)
            + '<span class="nav-label text-xs font-medium">' + (isDark ? 'Light mode' : 'Dark mode') + '</span>'
            + '<span class="nav-tip bg-gray-800 dark:bg-gray-200 text-white dark:text-gray-900 shadow-lg">' + (isDark ? 'Light mode' : 'Dark mode') + '</span>'
            + '</button>'
            // Collapse
            + '<button id="seerai-collapse-btn" class="nav-item relative w-full flex items-center gap-3 px-2.5 py-2 rounded-lg text-sm transition-colors text-gray-500 dark:text-gray-400 hover:bg-gray-100/80 dark:hover:bg-gray-800/60 hover:text-gray-900 dark:hover:text-gray-200 cursor-pointer">'
            + ico.chevL
            + '<span class="nav-label text-xs font-medium">Collapse <kbd class="ml-1 text-[0.6rem] px-1 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400 font-mono">&#8984;B</kbd></span>'
            + '<span class="nav-tip bg-gray-800 dark:bg-gray-200 text-white dark:text-gray-900 shadow-lg">Expand</span>'
            + '</button>'
            + '</div>'

            + '<div class="h-px mx-3 bg-gray-100 dark:bg-gray-800 shrink-0"></div>'

            // User
            + '<button id="seerai-user-btn" class="w-full flex items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/60 shrink-0 cursor-pointer">'
            + '<div class="w-8 h-8 rounded-full ' + avatarBg + ' flex items-center justify-center text-xs font-bold text-white shrink-0"' + avatarStyle + '>' + initials + '</div>'
            + '<div class="user-info min-w-0">'
            + '<div class="text-sm font-medium text-gray-700 dark:text-gray-200 truncate flex items-center">' + (user ? esc(user.user_id) : 'Select user') + ' ' + roleBadge + '</div>'
            + '<div class="text-[0.65rem] text-gray-400 truncate">' + esc(userSub) + '</div>'
            + '</div></button>';

        // Wire events
        document.getElementById('seerai-ds-btn').addEventListener('click', openDatasourceMenu);
        document.getElementById('seerai-theme-btn').addEventListener('click', function () {
            applyTheme(getTheme() === 'dark' ? 'light' : 'dark');
            renderSidebar();
        });
        document.getElementById('seerai-collapse-btn').addEventListener('click', toggleCollapse);
        document.getElementById('seerai-user-btn').addEventListener('click', openSwitcher);

        sidebar.querySelectorAll('nav a').forEach(function (a) {
            a.addEventListener('click', closeMobile);
        });
    }

    // --- Toggle collapse ---
    function toggleCollapse() {
        var wasExpanded = sbExpanded();
        setSbExpanded(!wasExpanded);
        sidebar.classList.toggle('collapsed', wasExpanded);
        document.body.classList.toggle('sb-collapsed', wasExpanded);
    }

    function closeMobile() {
        sidebar.classList.remove('mobile-open');
        backdrop.classList.remove('visible');
    }

    // --- Keyboard shortcut: Cmd/Ctrl+B ---
    document.addEventListener('keydown', function (e) {
        if (e.key === 'b' && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            if (window.innerWidth < 1024) {
                if (sidebar.classList.contains('mobile-open')) {
                    closeMobile();
                } else {
                    sidebar.classList.add('mobile-open');
                    backdrop.classList.add('visible');
                }
            } else {
                toggleCollapse();
            }
        }
    });

    // --- Datasource menu ---
    function openDatasourceMenu() {
        var old = document.getElementById('seerai-ds-menu');
        if (old) { old.remove(); return; }

        var btn = document.getElementById('seerai-ds-btn');
        var rect = btn.getBoundingClientRect();

        var menu = document.createElement('div');
        menu.id = 'seerai-ds-menu';
        menu.className = 'fixed z-[2000] w-48 rounded-lg border shadow-xl bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-sm overflow-hidden';
        menu.style.bottom = (window.innerHeight - rect.bottom) + 'px';
        menu.style.left = (rect.right + 8) + 'px';

        var ds = _dsInfo || { source: 'firestore', local_available: false };
        var items = [
            { id: 'local', label: 'Local', desc: ds.local_available ? 'From snapshot' : 'Not downloaded' },
            { id: 'firestore', label: 'Firestore', desc: 'Live database' },
        ];

        var html = '';
        for (var i = 0; i < items.length; i++) {
            var it = items[i];
            var active = ds.source === it.id;
            var bg = active ? 'bg-blue-50 dark:bg-blue-900/20' : 'hover:bg-gray-50 dark:hover:bg-gray-700/50';
            var check = active ? '<span class="text-blue-500">&#10003;</span>' : '<span class="w-4"></span>';
            html += '<div class="flex items-center gap-2 px-3 py-2.5 cursor-pointer transition-colors ' + bg + '" data-ds="' + it.id + '">'
                + check + '<div><div class="font-medium text-gray-800 dark:text-gray-200">' + it.label + '</div>'
                + '<div class="text-xs text-gray-400">' + it.desc + '</div></div></div>';
        }
        menu.innerHTML = html;
        document.body.appendChild(menu);

        var menuRect = menu.getBoundingClientRect();
        if (menuRect.right > window.innerWidth) {
            menu.style.left = ''; menu.style.right = '8px';
        }
        if (menuRect.top < 0) {
            menu.style.bottom = ''; menu.style.top = rect.top + 'px';
        }

        menu.querySelectorAll('[data-ds]').forEach(function (el) {
            el.addEventListener('click', function () {
                var target = el.dataset.ds;
                menu.remove();
                if (target === ds.source) return;

                if (target === 'local' && !ds.local_available) {
                    var dsBtn = document.getElementById('seerai-ds-btn');
                    var lbl = dsBtn.querySelector('.nav-label');
                    if (lbl) lbl.textContent = 'Downloading...';
                    downloadSnapshot().then(function () {
                        _dsInfo = { source: 'local', local_available: true };
                        renderSidebar();
                        window.location.reload();
                    }).catch(function () {
                        if (lbl) lbl.textContent = 'Error';
                    });
                } else {
                    switchDatasource(target).then(function () {
                        renderSidebar();
                        window.location.reload();
                    });
                }
            });
        });

        var closeMenu = function (e) {
            if (!menu.contains(e.target) && e.target !== btn && !btn.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }
        };
        setTimeout(function () { document.addEventListener('click', closeMenu); }, 0);
    }

    // --- User switcher modal ---
    function openSwitcher() {
        var overlay = document.createElement('div');
        overlay.className = 'fixed inset-0 z-[2000] bg-black/50 flex items-start justify-center pt-16';
        overlay.addEventListener('click', function (e) { if (e.target === overlay) overlay.remove(); });

        var modal = document.createElement('div');
        modal.className = 'w-[420px] max-w-[90vw] max-h-[70vh] overflow-y-auto rounded-xl border shadow-2xl bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700';
        modal.innerHTML =
            '<div class="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">'
            + '<h3 class="text-sm font-semibold text-gray-900 dark:text-white">Switch user</h3>'
            + '<button class="seerai-switcher-close text-gray-400 hover:text-gray-700 dark:hover:text-white text-lg px-1 cursor-pointer">&times;</button>'
            + '</div>'
            + '<input class="w-full px-4 py-2.5 text-sm border-b outline-none bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400" placeholder="Search users..." autofocus />'
            + '<div class="seerai-switcher-list pb-2">'
            + '<div class="px-4 py-6 text-center text-gray-400 text-sm">Loading...</div>'
            + '</div>';
        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        modal.querySelector('.seerai-switcher-close').addEventListener('click', function () { overlay.remove(); });

        var dataPromise;
        if (_allUsers.length && Object.keys(_companyMap).length) {
            dataPromise = Promise.resolve();
        } else {
            dataPromise = loadCompanyData();
        }

        dataPromise.then(function () {
            var users = _allUsers;
            var currentUser = getCurrentUser();
            var listEl = modal.querySelector('.seerai-switcher-list');
            var searchEl = modal.querySelector('input');

            function renderList(filter) {
                var filtered = filter
                    ? users.filter(function (u) { return u.user_id.toLowerCase().includes(filter.toLowerCase()); })
                    : users;

                var companies = {};
                for (var i = 0; i < filtered.length; i++) {
                    var u = filtered[i];
                    var companyId = _companyMap[u.org_id] || 'unknown';
                    if (!companies[companyId]) companies[companyId] = [];
                    companies[companyId].push(u);
                }

                var html = '';

                // Admin option
                if (!filter || 'admin'.includes(filter.toLowerCase()) || 'platform'.includes(filter.toLowerCase())) {
                    var isCurrentAdmin = currentUser && currentUser.role === 'admin';
                    var adminBg = isCurrentAdmin ? 'bg-blue-50 dark:bg-blue-900/20' : 'hover:bg-gray-50 dark:hover:bg-gray-700/50';
                    html += '<div class="px-4 pt-3 pb-1 text-[0.65rem] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-medium">Platform</div>';
                    html += '<div class="flex items-center justify-between px-4 py-2 cursor-pointer transition-colors ' + adminBg + '" data-uid="admin" data-role="admin" data-org="" data-company="">'
                        + '<span class="text-gray-800 dark:text-gray-200 text-sm flex items-center gap-2">'
                        + '<span class="w-5 h-5 rounded-full inline-flex items-center justify-center bg-red-500 text-white text-[0.6rem] font-bold shrink-0">S</span>'
                        + 'Platform Admin'
                        + '<span class="text-[0.6rem] ml-0.5 px-1 py-0.5 rounded font-semibold uppercase bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400">admin</span>'
                        + '</span>'
                        + (isCurrentAdmin ? '<span class="text-xs text-gray-400">current</span>' : '')
                        + '</div>';
                }

                if (!filtered.length && !html) {
                    listEl.innerHTML = '<div class="px-4 py-6 text-center text-gray-400 text-sm">No matches</div>';
                    return;
                }

                var companyIds = Object.keys(companies);
                for (var ci = 0; ci < companyIds.length; ci++) {
                    var cid = companyIds[ci];
                    var brand = COMPANY_BRANDS[cid];
                    var groupLabel = brand
                        ? '<span class="inline-flex items-center gap-1.5">'
                            + '<span class="w-4 h-4 rounded-full inline-flex items-center justify-center text-white text-[0.5rem] font-bold" style="background:' + brand.color + '">' + brand.initial + '</span>'
                            + brand.name + '</span>'
                        : esc(cid);
                    html += '<div class="px-4 pt-3 pb-1 text-[0.65rem] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-medium">' + groupLabel + '</div>';

                    var groupUsers = companies[cid];
                    for (var j = 0; j < groupUsers.length; j++) {
                        var gu = groupUsers[j];
                        var isCurrent = currentUser && currentUser.user_id === gu.user_id;
                        var badge = gu.role === 'exec'
                            ? '<span class="text-[0.6rem] ml-1.5 px-1 py-0.5 rounded font-semibold uppercase bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">exec</span>'
                            : '';
                        var orgLabel = (_orgNames[gu.org_id] && brand && _orgNames[gu.org_id] !== brand.name)
                            ? '<span class="text-[0.6rem] text-gray-400 ml-1.5">' + esc(_orgNames[gu.org_id]) + '</span>'
                            : '';
                        var bg = isCurrent ? 'bg-blue-50 dark:bg-blue-900/20' : 'hover:bg-gray-50 dark:hover:bg-gray-700/50';
                        html += '<div class="flex items-center justify-between px-4 py-2 cursor-pointer transition-colors ' + bg + '" data-uid="' + esc(gu.user_id) + '" data-role="' + gu.role + '" data-org="' + esc(gu.org_id || '') + '" data-company="' + esc(cid) + '">'
                            + '<span class="text-gray-800 dark:text-gray-200 text-sm">' + esc(gu.user_id) + badge + orgLabel + '</span>'
                            + (isCurrent ? '<span class="text-xs text-gray-400">current</span>' : '')
                            + '</div>';
                    }
                }
                listEl.innerHTML = html;

                listEl.querySelectorAll('[data-uid]').forEach(function (item) {
                    item.addEventListener('click', function () {
                        var role = item.dataset.role;
                        var uid = item.dataset.uid;
                        var company = item.dataset.company || null;
                        setCurrentUser({
                            user_id: uid,
                            role: role,
                            org_id: item.dataset.org || null,
                            company: company,
                        });
                        overlay.remove();
                        renderSidebar();
                        if (role === 'admin') {
                            window.location.href = '/';
                        } else if (role === 'exec') {
                            window.location.href = '/exec';
                        } else {
                            window.location.href = '/my/' + encodeURIComponent(uid);
                        }
                    });
                });
            }

            renderList('');
            searchEl.addEventListener('input', function () { renderList(searchEl.value); });
            searchEl.focus();
        });

        var onKey = function (e) {
            if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', onKey); }
        };
        document.addEventListener('keydown', onKey);
    }

    // --- Init ---
    renderSidebar();
    renderMobileBar();

    window.seerai.ready = Promise.all([fetchDatasource(), loadCompanyData()]).then(function () {
        var user = getCurrentUser();
        if (user && user.org_id && !user.company) {
            user.company = _companyMap[user.org_id] || null;
            setCurrentUser(user);
        }
        renderSidebar();
        checkPageAccess();
    });

    if (!getCurrentUser()) openSwitcher();
})();
