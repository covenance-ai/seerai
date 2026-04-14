/**
 * Shared navigation bar with user switcher, theme toggle, and company-aware access control.
 * Include via <script src="/static/nav.js"></script> in every page.
 * Requires Tailwind CDN loaded before this script.
 */
(function () {
    const USER_KEY = 'seerai_user';
    const THEME_KEY = 'seerai_theme';

    // --- Company branding ---
    const COMPANY_BRANDS = {
        'acme': { name: 'Acme Corp', color: '#3B82F6', initial: 'A' },
        'initech': { name: 'Initech', color: '#10B981', initial: 'I' },
    };

    let _companyMap = {};      // org_id → root_org_id
    let _userCompanyMap = {};  // user_id → root_org_id
    let _orgNames = {};        // org_id → display name
    let _allUsers = [];
    let _dsInfo = null;

    // --- Public API (available after seerai.ready resolves) ---
    window.seerai = window.seerai || {};
    window.seerai.COMPANY_BRANDS = COMPANY_BRANDS;

    window.seerai.companyBadge = function (rootOrgId, opts) {
        opts = opts || {};
        const brand = COMPANY_BRANDS[rootOrgId];
        if (!brand) return '';
        const sz = opts.size === 'lg' ? 'w-7 h-7 text-xs' : 'w-5 h-5 text-[0.6rem]';
        const nameHtml = opts.showName !== false
            ? '<span class="text-xs text-gray-500 dark:text-gray-400">' + brand.name + '</span>'
            : '';
        return '<span class="inline-flex items-center gap-1.5">'
            + '<span class="' + sz + ' rounded-full inline-flex items-center justify-center text-white font-bold shrink-0" style="background:' + brand.color + '">' + brand.initial + '</span>'
            + nameHtml
            + '</span>';
    };

    window.seerai.getUserCompany = function (userId) {
        return _userCompanyMap[userId] || null;
    };

    window.seerai.getCompany = function (orgId) {
        return _companyMap[orgId] || null;
    };

    window.seerai.getCurrentUser = getCurrentUser;

    /** Check if current user can view data belonging to targetUserId. */
    window.seerai.canAccessUser = function (targetUserId) {
        const user = getCurrentUser();
        if (!user) return false;
        if (user.role === 'admin') return true;
        if (user.user_id === targetUserId) return true;
        const myCompany = user.company;
        const targetCompany = _userCompanyMap[targetUserId];
        return myCompany && targetCompany && myCompany === targetCompany;
    };

    // --- Data source ---
    function fetchDatasource() {
        return fetch('/api/datasource').then(r => r.json()).then(info => { _dsInfo = info; return info; });
    }

    function switchDatasource(source) {
        return fetch('/api/datasource', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source: source, local_available: false }),
        }).then(r => r.json()).then(info => { _dsInfo = info; return info; });
    }

    function downloadSnapshot() {
        return fetch('/api/datasource/download', { method: 'POST' }).then(r => r.json());
    }

    // --- Company data ---
    async function loadCompanyData() {
        const [roots, users] = await Promise.all([
            fetch('/api/orgs').then(r => r.json()),
            fetch('/api/users').then(r => r.json()),
        ]);
        _allUsers = users;

        const trees = await Promise.all(
            roots.map(r => fetch('/api/orgs/' + encodeURIComponent(r.org_id) + '/tree').then(t => t.json()))
        );

        function walk(node, rootId) {
            _companyMap[node.node.org_id] = rootId;
            _orgNames[node.node.org_id] = node.node.name;
            node.children.forEach(function (c) { walk(c, rootId); });
        }
        trees.forEach(function (t) { walk(t, t.node.org_id); });

        for (var i = 0; i < users.length; i++) {
            var u = users[i];
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
        catch { return null; }
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

        // Root page: admin only
        if (path === '/') {
            if (!isAdmin) {
                window.location.replace(user.role === 'exec' ? '/exec' : '/my/' + encodeURIComponent(user.user_id));
            }
            return;
        }

        // /sessions/{user_id} or /session/{user_id}/{sid} — admin or same company
        var sessMatch = path.match(/^\/(sessions?)\//);
        if (sessMatch && !isAdmin) {
            var parts = path.split('/');
            var targetId = decodeURIComponent(parts[2]);
            var targetCompany = _userCompanyMap[targetId];
            if (targetCompany && user.company && targetCompany !== user.company) {
                window.location.replace('/my/' + encodeURIComponent(user.user_id));
                return;
            }
        }

        // /exec pages — admin or exec
        if (path.startsWith('/exec') && !isAdmin && user.role !== 'exec') {
            window.location.replace('/my/' + encodeURIComponent(user.user_id));
        }
    }

    // --- Nav bar ---
    var nav = document.createElement('nav');
    nav.className = 'fixed top-0 inset-x-0 z-50 h-11 flex items-center px-4 gap-4 text-sm border-b bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700/60';
    document.body.prepend(nav);
    document.body.classList.add('pt-14');

    function renderNav() {
        var user = getCurrentUser();
        var isAdmin = user && user.role === 'admin';
        var isExec = user && user.role === 'exec';
        var path = window.location.pathname;
        var isDark = getTheme() === 'dark';

        var linkBase = 'transition-colors hover:text-gray-900 dark:hover:text-white';
        var linkActive = 'text-gray-900 dark:text-white font-medium';
        var linkInactive = 'text-gray-500 dark:text-gray-400';

        var links = '';

        // Admin: All Users link
        if (isAdmin) {
            var allCls = path === '/' ? linkActive : linkInactive;
            links += '<a href="/" class="' + linkBase + ' ' + allCls + '">All Users</a>';
        }

        // Admin or Exec: Dashboard + Insights + Costs
        if (isAdmin || isExec) {
            var dashCls = (path.startsWith('/exec') && !path.startsWith('/exec/costs') && !path.startsWith('/exec/insights')) ? linkActive : linkInactive;
            links += '<a href="/exec" class="' + linkBase + ' ' + dashCls + '">Dashboard</a>';
            var insCls = path.startsWith('/exec/insights') ? linkActive : linkInactive;
            links += '<a href="/exec/insights" class="' + linkBase + ' ' + insCls + '">Insights</a>';
            var costCls = path.startsWith('/exec/costs') ? linkActive : linkInactive;
            links += '<a href="/exec/costs" class="' + linkBase + ' ' + costCls + '">Costs</a>';
        }

        // All logged-in users: My Sessions
        if (user && user.role !== 'admin') {
            var myHref = '/my/' + encodeURIComponent(user.user_id);
            var cls = path.startsWith('/my/') ? linkActive : linkInactive;
            links += '<a href="' + myHref + '" class="' + linkBase + ' ' + cls + '">My Sessions</a>';
        }

        // Role badge
        var roleBadge = '';
        if (user) {
            if (user.role === 'admin') {
                roleBadge = '<span class="text-[0.65rem] px-1.5 py-0.5 rounded font-semibold uppercase bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400">admin</span>';
            } else if (user.role === 'exec') {
                roleBadge = '<span class="text-[0.65rem] px-1.5 py-0.5 rounded font-semibold uppercase bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">exec</span>';
            } else {
                roleBadge = '<span class="text-[0.65rem] px-1.5 py-0.5 rounded font-semibold uppercase bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">user</span>';
            }
        }

        // Company badge in nav
        var companyHtml = '';
        if (user && user.company && COMPANY_BRANDS[user.company]) {
            companyHtml = window.seerai.companyBadge(user.company, { showName: false });
        }

        var userBtn = user
            ? '<button id="seerai-user-btn" class="flex items-center gap-2 px-3 py-1.5 rounded-lg border cursor-pointer transition-colors bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-blue-400 dark:hover:border-blue-500">'
                + companyHtml
                + roleBadge
                + '<span class="text-gray-700 dark:text-gray-200">' + esc(user.user_id) + '</span>'
                + '<span class="text-gray-400">&#9662;</span>'
                + '</button>'
            : '<button id="seerai-user-btn" class="flex items-center gap-2 px-3 py-1.5 rounded-lg border cursor-pointer transition-colors bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-blue-400">'
                + '<span class="text-gray-400">Select user &#9662;</span>'
                + '</button>';

        // Sun/moon toggle
        var themeBtn = '<button id="seerai-theme-btn" class="p-1.5 rounded-lg transition-colors text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800" title="Toggle theme">'
            + (isDark
                ? '<svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3v1m0 16v1m8.66-13.66l-.71.71M4.05 19.95l-.71.71M21 12h-1M4 12H3m16.66 7.66l-.71-.71M4.05 4.05l-.71-.71M16 12a4 4 0 11-8 0 4 4 0 018 0z"/></svg>'
                : '<svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/></svg>')
            + '</button>';

        // Data source selector
        var ds = _dsInfo;
        var dsLabel = ds ? ds.source : '...';
        var dsIcon = dsLabel === 'local'
            ? '<svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 7v10c0 2 1 3 3 3h10c2 0 3-1 3-3V7M4 7c0-2 1-3 3-3h10c2 0 3 1 3 3M4 7h16M8 12h.01M12 12h.01M16 12h.01"/></svg>'
            : '<svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z"/></svg>';
        var dsBtn = '<button id="seerai-ds-btn" class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border cursor-pointer transition-colors text-xs font-medium bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-blue-400 dark:hover:border-blue-500 text-gray-600 dark:text-gray-300" title="Data source: ' + dsLabel + '">'
            + dsIcon
            + '<span>' + dsLabel + '</span>'
            + '<span class="text-gray-400 text-[0.6rem]">&#9662;</span>'
            + '</button>';

        var homeHref = '/';
        if (user && !isAdmin) {
            homeHref = isExec ? '/exec' : '/my/' + encodeURIComponent(user.user_id);
        }
        nav.innerHTML = '<a href="' + homeHref + '" class="font-semibold text-gray-900 dark:text-white text-base mr-2">seerai</a>'
            + '<div class="flex gap-3 flex-1">' + links + '</div>'
            + themeBtn
            + dsBtn
            + userBtn;

        document.getElementById('seerai-ds-btn').addEventListener('click', openDatasourceMenu);
        document.getElementById('seerai-user-btn').addEventListener('click', openSwitcher);
        document.getElementById('seerai-theme-btn').addEventListener('click', function () {
            var next = getTheme() === 'dark' ? 'light' : 'dark';
            applyTheme(next);
            renderNav();
        });
    }

    // --- Data source menu ---
    function openDatasourceMenu() {
        var old = document.getElementById('seerai-ds-menu');
        if (old) { old.remove(); return; }

        var btn = document.getElementById('seerai-ds-btn');
        var rect = btn.getBoundingClientRect();

        var menu = document.createElement('div');
        menu.id = 'seerai-ds-menu';
        menu.className = 'fixed z-[2000] w-48 rounded-lg border shadow-xl bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 text-sm overflow-hidden';
        menu.style.top = (rect.bottom + 6) + 'px';
        menu.style.right = (window.innerWidth - rect.right) + 'px';

        var ds = _dsInfo || { source: 'firestore', local_available: false };
        var items = [
            { id: 'local', label: 'Local', desc: ds.local_available ? 'From snapshot' : 'Not downloaded' },
            { id: 'firestore', label: 'Firestore', desc: 'Live database' },
        ];

        var html = '';
        for (var i = 0; i < items.length; i++) {
            var item = items[i];
            var active = ds.source === item.id;
            var bg = active ? 'bg-blue-50 dark:bg-blue-900/20' : 'hover:bg-gray-50 dark:hover:bg-gray-700/50';
            var check = active ? '<span class="text-blue-500">&#10003;</span>' : '<span class="w-3"></span>';
            html += '<div class="flex items-center gap-2 px-3 py-2.5 cursor-pointer ' + bg + '" data-ds="' + item.id + '">'
                + check
                + '<div><div class="font-medium text-gray-800 dark:text-gray-200">' + item.label + '</div>'
                + '<div class="text-xs text-gray-400">' + item.desc + '</div></div>'
                + '</div>';
        }
        menu.innerHTML = html;
        document.body.appendChild(menu);

        menu.querySelectorAll('[data-ds]').forEach(function (el) {
            el.addEventListener('click', function () {
                var target = el.dataset.ds;
                menu.remove();
                if (target === ds.source) return;

                if (target === 'local' && !ds.local_available) {
                    var btn2 = document.getElementById('seerai-ds-btn');
                    btn2.textContent = '...';
                    btn2.title = 'Downloading snapshot...';
                    downloadSnapshot().then(function () {
                        _dsInfo = { source: 'local', local_available: true };
                        renderNav();
                        window.location.reload();
                    }).catch(function (err) {
                        btn2.textContent = 'ERR';
                        btn2.title = 'Download failed: ' + err.message;
                    });
                } else {
                    switchDatasource(target).then(function () {
                        renderNav();
                        window.location.reload();
                    });
                }
            });
        });

        var closeMenu = function (e) {
            if (!menu.contains(e.target) && e.target !== btn) {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }
        };
        setTimeout(function () { document.addEventListener('click', closeMenu); }, 0);
    }

    // --- Switcher modal ---
    function openSwitcher() {
        var overlay = document.createElement('div');
        overlay.className = 'fixed inset-0 z-[2000] bg-black/50 flex items-start justify-center pt-16';
        overlay.addEventListener('click', function (e) { if (e.target === overlay) overlay.remove(); });

        var modal = document.createElement('div');
        modal.className = 'w-[420px] max-h-[70vh] overflow-y-auto rounded-xl border shadow-2xl bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700';
        modal.innerHTML = '<div class="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">'
            + '<h3 class="text-sm font-semibold text-gray-900 dark:text-white">Switch user</h3>'
            + '<button class="seerai-switcher-close text-gray-400 hover:text-gray-700 dark:hover:text-white text-lg px-1">&times;</button>'
            + '</div>'
            + '<input class="w-full px-4 py-2.5 text-sm border-b outline-none bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400" placeholder="Search users..." autofocus />'
            + '<div class="seerai-switcher-list pb-2">'
            + '<div class="px-4 py-6 text-center text-gray-400 text-sm">Loading...</div>'
            + '</div>';
        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        modal.querySelector('.seerai-switcher-close').addEventListener('click', function () { overlay.remove(); });

        // Use cached data if available, otherwise fetch
        var dataPromise;
        if (_allUsers.length && Object.keys(_companyMap).length) {
            dataPromise = Promise.resolve({ users: _allUsers });
        } else {
            dataPromise = loadCompanyData().then(function () { return { users: _allUsers }; });
        }

        dataPromise.then(function (data) {
            var users = data.users;
            var currentUser = getCurrentUser();
            var listEl = modal.querySelector('.seerai-switcher-list');
            var searchEl = modal.querySelector('input');

            function renderList(filter) {
                var filtered = filter
                    ? users.filter(function (u) { return u.user_id.toLowerCase().includes(filter.toLowerCase()); })
                    : users;

                // Group by company (root org)
                var companies = {};
                for (var i = 0; i < filtered.length; i++) {
                    var u = filtered[i];
                    var companyId = _companyMap[u.org_id] || 'unknown';
                    if (!companies[companyId]) companies[companyId] = [];
                    companies[companyId].push(u);
                }

                var html = '';

                // Admin option (always show unless filtered out)
                if (!filter || 'admin'.includes(filter.toLowerCase()) || 'platform'.includes(filter.toLowerCase())) {
                    var isCurrentAdmin = currentUser && currentUser.role === 'admin';
                    var adminBg = isCurrentAdmin ? 'bg-blue-50 dark:bg-blue-900/20' : 'hover:bg-gray-50 dark:hover:bg-gray-700/50';
                    html += '<div class="px-4 pt-3 pb-1 text-[0.65rem] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-medium">Platform</div>';
                    html += '<div class="flex items-center justify-between px-4 py-2 cursor-pointer ' + adminBg + '" data-uid="admin" data-role="admin" data-org="" data-company="">'
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

                // Company groups
                var companyIds = Object.keys(companies);
                for (var ci = 0; ci < companyIds.length; ci++) {
                    var cid = companyIds[ci];
                    var brand = COMPANY_BRANDS[cid];
                    var groupLabel = brand
                        ? '<span class="inline-flex items-center gap-1.5">'
                            + '<span class="w-4 h-4 rounded-full inline-flex items-center justify-center text-white text-[0.5rem] font-bold" style="background:' + brand.color + '">' + brand.initial + '</span>'
                            + brand.name
                            + '</span>'
                        : esc(cid);

                    html += '<div class="px-4 pt-3 pb-1 text-[0.65rem] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-medium">' + groupLabel + '</div>';

                    var groupUsers = companies[cid];
                    for (var j = 0; j < groupUsers.length; j++) {
                        var u = groupUsers[j];
                        var isCurrent = currentUser && currentUser.user_id === u.user_id;
                        var badge = u.role === 'exec'
                            ? '<span class="text-[0.6rem] ml-1.5 px-1 py-0.5 rounded font-semibold uppercase bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">exec</span>'
                            : '';
                        var orgLabel = (_orgNames[u.org_id] && _orgNames[u.org_id] !== (brand ? brand.name : ''))
                            ? '<span class="text-[0.6rem] text-gray-400 ml-1.5">' + esc(_orgNames[u.org_id]) + '</span>'
                            : '';
                        var bg = isCurrent ? 'bg-blue-50 dark:bg-blue-900/20' : 'hover:bg-gray-50 dark:hover:bg-gray-700/50';
                        html += '<div class="flex items-center justify-between px-4 py-2 cursor-pointer ' + bg + '" data-uid="' + esc(u.user_id) + '" data-role="' + u.role + '" data-org="' + esc(u.org_id || '') + '" data-company="' + esc(cid) + '">'
                            + '<span class="text-gray-800 dark:text-gray-200 text-sm">' + esc(u.user_id) + badge + orgLabel + '</span>'
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

    // --- Initialization ---
    renderNav(); // render immediately with whatever state we have

    window.seerai.ready = Promise.all([fetchDatasource(), loadCompanyData()]).then(function () {
        // Re-derive company for current user if not set
        var user = getCurrentUser();
        if (user && user.org_id && !user.company) {
            user.company = _companyMap[user.org_id] || null;
            setCurrentUser(user);
        }
        renderNav();
        checkPageAccess();
    });

    if (!getCurrentUser()) openSwitcher();
})();
