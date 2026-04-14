/**
 * Shared navigation bar with user switcher and theme toggle.
 * Include via <script src="/static/nav.js"></script> in every page.
 * Requires Tailwind CDN loaded before this script.
 */
(function () {
    const USER_KEY = 'seerai_user';
    const THEME_KEY = 'seerai_theme';

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
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    // --- Nav bar ---
    const nav = document.createElement('nav');
    nav.className = 'fixed top-0 inset-x-0 z-50 h-11 flex items-center px-4 gap-4 text-sm border-b bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700/60';
    document.body.prepend(nav);
    document.body.classList.add('pt-14');

    function renderNav() {
        const user = getCurrentUser();
        const isExec = user && user.role === 'exec';
        const path = window.location.pathname;
        const isDark = getTheme() === 'dark';

        const linkBase = 'transition-colors hover:text-gray-900 dark:hover:text-white';
        const linkActive = 'text-gray-900 dark:text-white font-medium';
        const linkInactive = 'text-gray-500 dark:text-gray-400';

        let links = '';
        if (isExec) {
            const dashCls = (path.startsWith('/exec') && !path.startsWith('/exec/costs')) ? linkActive : linkInactive;
            links += `<a href="/exec" class="${linkBase} ${dashCls}">Dashboard</a>`;
            const costCls = path.startsWith('/exec/costs') ? linkActive : linkInactive;
            links += `<a href="/exec/costs" class="${linkBase} ${costCls}">Costs</a>`;
        }
        if (user) {
            const myHref = `/my/${encodeURIComponent(user.user_id)}`;
            const cls = path.startsWith('/my/') ? linkActive : linkInactive;
            links += `<a href="${myHref}" class="${linkBase} ${cls}">My Sessions</a>`;
        }
        const allCls = path === '/' ? linkActive : linkInactive;
        links += `<a href="/" class="${linkBase} ${allCls}">All Users</a>`;

        const roleBadge = user
            ? (user.role === 'exec'
                ? '<span class="text-[0.65rem] px-1.5 py-0.5 rounded font-semibold uppercase bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">exec</span>'
                : '<span class="text-[0.65rem] px-1.5 py-0.5 rounded font-semibold uppercase bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">user</span>')
            : '';

        const userBtn = user
            ? `<button id="seerai-user-btn" class="flex items-center gap-2 px-3 py-1.5 rounded-lg border cursor-pointer transition-colors bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-blue-400 dark:hover:border-blue-500">
                ${roleBadge}
                <span class="text-gray-700 dark:text-gray-200">${esc(user.user_id)}</span>
                <span class="text-gray-400">&#9662;</span>
               </button>`
            : `<button id="seerai-user-btn" class="flex items-center gap-2 px-3 py-1.5 rounded-lg border cursor-pointer transition-colors bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-blue-400">
                <span class="text-gray-400">Select user &#9662;</span>
               </button>`;

        // Sun/moon toggle
        const themeBtn = `<button id="seerai-theme-btn" class="p-1.5 rounded-lg transition-colors text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800" title="Toggle theme">
            ${isDark
                ? '<svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3v1m0 16v1m8.66-13.66l-.71.71M4.05 19.95l-.71.71M21 12h-1M4 12H3m16.66 7.66l-.71-.71M4.05 4.05l-.71-.71M16 12a4 4 0 11-8 0 4 4 0 018 0z"/></svg>'
                : '<svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/></svg>'
            }
        </button>`;

        nav.innerHTML = `
            <a href="/" class="font-semibold text-gray-900 dark:text-white text-base mr-2">seerai</a>
            <div class="flex gap-3 flex-1">${links}</div>
            ${themeBtn}
            ${userBtn}
        `;

        document.getElementById('seerai-user-btn').addEventListener('click', openSwitcher);
        document.getElementById('seerai-theme-btn').addEventListener('click', () => {
            const next = getTheme() === 'dark' ? 'light' : 'dark';
            applyTheme(next);
            renderNav();
        });
    }

    // --- Switcher modal ---
    function openSwitcher() {
        const overlay = document.createElement('div');
        overlay.className = 'fixed inset-0 z-[2000] bg-black/50 flex items-start justify-center pt-16';
        overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

        const modal = document.createElement('div');
        modal.className = 'w-[420px] max-h-[70vh] overflow-y-auto rounded-xl border shadow-2xl bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700';
        modal.innerHTML = `
            <div class="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Switch user</h3>
                <button class="seerai-switcher-close text-gray-400 hover:text-gray-700 dark:hover:text-white text-lg px-1">&times;</button>
            </div>
            <input class="w-full px-4 py-2.5 text-sm border-b outline-none bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400" placeholder="Search users..." autofocus />
            <div class="seerai-switcher-list pb-2">
                <div class="px-4 py-6 text-center text-gray-400 text-sm">Loading...</div>
            </div>
        `;
        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        modal.querySelector('.seerai-switcher-close').addEventListener('click', () => overlay.remove());

        Promise.all([
            fetch('/api/users').then(r => r.json()),
            fetch('/api/orgs').then(r => r.json()).then(roots =>
                Promise.all(roots.map(r => fetch(`/api/orgs/${encodeURIComponent(r.org_id)}/tree`).then(r => r.json())))
            ),
        ]).then(([users, trees]) => {
            const orgNames = {};
            function walkTree(t) { orgNames[t.node.org_id] = t.node.name; t.children.forEach(walkTree); }
            trees.forEach(walkTree);

            const currentUser = getCurrentUser();
            const listEl = modal.querySelector('.seerai-switcher-list');
            const searchEl = modal.querySelector('input');

            function renderList(filter) {
                const filtered = filter
                    ? users.filter(u => u.user_id.toLowerCase().includes(filter.toLowerCase()))
                    : users;

                const groups = {};
                for (const u of filtered) {
                    const orgName = orgNames[u.org_id] || u.org_id || 'Unassigned';
                    if (!groups[orgName]) groups[orgName] = [];
                    groups[orgName].push(u);
                }

                if (!filtered.length) {
                    listEl.innerHTML = '<div class="px-4 py-6 text-center text-gray-400 text-sm">No matches</div>';
                    return;
                }

                let html = '';
                for (const [group, groupUsers] of Object.entries(groups)) {
                    html += `<div class="px-4 pt-3 pb-1 text-[0.65rem] uppercase tracking-wider text-gray-400 dark:text-gray-500 font-medium">${esc(group)}</div>`;
                    for (const u of groupUsers) {
                        const isCurrent = currentUser && currentUser.user_id === u.user_id;
                        const badge = u.role === 'exec'
                            ? '<span class="text-[0.6rem] ml-1.5 px-1 py-0.5 rounded font-semibold uppercase bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400">exec</span>'
                            : '';
                        const bg = isCurrent ? 'bg-blue-50 dark:bg-blue-900/20' : 'hover:bg-gray-50 dark:hover:bg-gray-700/50';
                        html += `<div class="flex items-center justify-between px-4 py-2 cursor-pointer ${bg}" data-uid="${esc(u.user_id)}" data-role="${u.role}" data-org="${esc(u.org_id || '')}">
                            <span class="text-gray-800 dark:text-gray-200 text-sm">${esc(u.user_id)}${badge}</span>
                            ${isCurrent ? '<span class="text-xs text-gray-400">current</span>' : ''}
                        </div>`;
                    }
                }
                listEl.innerHTML = html;

                listEl.querySelectorAll('[data-uid]').forEach(item => {
                    item.addEventListener('click', () => {
                        setCurrentUser({
                            user_id: item.dataset.uid,
                            role: item.dataset.role,
                            org_id: item.dataset.org || null,
                        });
                        overlay.remove();
                        if (item.dataset.role === 'exec') {
                            window.location.href = '/exec';
                        } else {
                            window.location.href = `/my/${encodeURIComponent(item.dataset.uid)}`;
                        }
                    });
                });
            }

            renderList('');
            searchEl.addEventListener('input', () => renderList(searchEl.value));
            searchEl.focus();
        });

        const onKey = (e) => { if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', onKey); } };
        document.addEventListener('keydown', onKey);
    }

    renderNav();
    if (!getCurrentUser()) openSwitcher();
})();
