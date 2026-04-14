/**
 * Shared navigation bar with user switcher.
 * Include via <script src="/static/nav.js"></script> in every page.
 *
 * Reads/writes localStorage key "seerai_user" (JSON: {user_id, role, org_id}).
 * Injects a top nav bar and handles user switching.
 */
(function () {
    const STORAGE_KEY = 'seerai_user';

    function getCurrentUser() {
        try { return JSON.parse(localStorage.getItem(STORAGE_KEY)); }
        catch { return null; }
    }

    function setCurrentUser(user) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
    }

    function esc(s) {
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    // Inject nav bar styles
    const style = document.createElement('style');
    style.textContent = `
        .seerai-nav {
            position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
            background: #161821; border-bottom: 1px solid #2a2d35;
            display: flex; align-items: center; padding: 0 1rem; height: 44px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 0.85rem; color: #e0e0e0;
        }
        .seerai-nav a { color: #60a5fa; text-decoration: none; }
        .seerai-nav a:hover { text-decoration: underline; }
        .seerai-nav .nav-brand { font-weight: 600; color: #fff; margin-right: 1.5rem; font-size: 0.95rem; }
        .seerai-nav .nav-links { display: flex; gap: 1rem; flex: 1; }
        .seerai-nav .nav-links a { color: #aaa; }
        .seerai-nav .nav-links a:hover, .seerai-nav .nav-links a.active { color: #fff; }
        .seerai-nav .nav-user {
            position: relative; cursor: pointer; padding: 0.3rem 0.6rem;
            border-radius: 6px; background: #1a1d25; border: 1px solid #2a2d35;
            display: flex; align-items: center; gap: 0.4rem;
        }
        .seerai-nav .nav-user:hover { border-color: #60a5fa; }
        .seerai-nav .role-badge {
            font-size: 0.7rem; padding: 0.1rem 0.35rem; border-radius: 3px;
            text-transform: uppercase; font-weight: 600;
        }
        .seerai-nav .role-exec { background: #3b2f0a; color: #fbbf24; }
        .seerai-nav .role-user { background: #1e3a5f; color: #93c5fd; }
        body { padding-top: 52px !important; }

        /* Switcher overlay */
        .seerai-switcher-overlay {
            position: fixed; inset: 0; z-index: 2000;
            background: rgba(0,0,0,0.6); display: flex; align-items: flex-start;
            justify-content: center; padding-top: 60px;
        }
        .seerai-switcher {
            background: #1a1d25; border: 1px solid #2a2d35; border-radius: 10px;
            width: 420px; max-height: 70vh; overflow-y: auto;
            box-shadow: 0 8px 32px rgba(0,0,0,0.5);
        }
        .seerai-switcher-header {
            padding: 0.8rem 1rem; border-bottom: 1px solid #2a2d35;
            display: flex; align-items: center; justify-content: space-between;
        }
        .seerai-switcher-header h3 { font-size: 0.95rem; color: #fff; margin: 0; }
        .seerai-switcher-close {
            background: none; border: none; color: #888; font-size: 1.2rem;
            cursor: pointer; padding: 0.2rem 0.4rem;
        }
        .seerai-switcher-close:hover { color: #fff; }
        .seerai-switcher-search {
            width: 100%; padding: 0.5rem 1rem; background: #0f1117;
            border: none; border-bottom: 1px solid #2a2d35;
            color: #e0e0e0; font-size: 0.85rem; outline: none;
        }
        .seerai-switcher-group {
            padding: 0.4rem 1rem 0.2rem; font-size: 0.7rem; color: #666;
            text-transform: uppercase; letter-spacing: 0.05em;
        }
        .seerai-switcher-item {
            padding: 0.5rem 1rem; cursor: pointer;
            display: flex; align-items: center; justify-content: space-between;
        }
        .seerai-switcher-item:hover { background: #252830; }
        .seerai-switcher-item.current { background: #1e3a5f33; }
        .seerai-switcher-item .name { color: #e0e0e0; }
        .seerai-switcher-item .meta { font-size: 0.75rem; color: #666; }
    `;
    document.head.appendChild(style);

    // Build nav bar
    const nav = document.createElement('div');
    nav.className = 'seerai-nav';
    document.body.prepend(nav);

    function renderNav() {
        const user = getCurrentUser();
        const isExec = user && user.role === 'exec';
        const path = window.location.pathname;

        let links = '';
        if (isExec) {
            links += `<a href="/exec" class="${path.startsWith('/exec') ? 'active' : ''}">Dashboard</a>`;
        }
        if (user) {
            const myHref = `/my/${encodeURIComponent(user.user_id)}`;
            links += `<a href="${myHref}" class="${path.startsWith('/my/') ? 'active' : ''}">My Sessions</a>`;
        }
        links += `<a href="/" class="${path === '/' ? 'active' : ''}">All Users</a>`;

        const userBtn = user
            ? `<div class="nav-user" id="seerai-user-btn">
                <span class="role-badge role-${user.role}">${user.role}</span>
                <span>${esc(user.user_id)}</span>
                <span style="color:#666">▾</span>
               </div>`
            : `<div class="nav-user" id="seerai-user-btn">
                <span style="color:#888">Select user ▾</span>
               </div>`;

        nav.innerHTML = `
            <a class="nav-brand" href="/">seerai</a>
            <div class="nav-links">${links}</div>
            ${userBtn}
        `;

        document.getElementById('seerai-user-btn').addEventListener('click', openSwitcher);
    }

    function openSwitcher() {
        const overlay = document.createElement('div');
        overlay.className = 'seerai-switcher-overlay';
        overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

        const modal = document.createElement('div');
        modal.className = 'seerai-switcher';
        modal.innerHTML = `
            <div class="seerai-switcher-header">
                <h3>Switch user</h3>
                <button class="seerai-switcher-close">&times;</button>
            </div>
            <input class="seerai-switcher-search" placeholder="Search users..." autofocus />
            <div class="seerai-switcher-list" style="padding-bottom:0.5rem;">
                <div style="padding:1rem;color:#666;text-align:center;">Loading...</div>
            </div>
        `;
        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        modal.querySelector('.seerai-switcher-close').addEventListener('click', () => overlay.remove());

        // Fetch users and orgs for grouping
        Promise.all([
            fetch('/api/users').then(r => r.json()),
            fetch('/api/orgs').then(r => r.json()).then(roots =>
                Promise.all(roots.map(r => fetch(`/api/orgs/${encodeURIComponent(r.org_id)}/tree`).then(r => r.json())))
            ),
        ]).then(([users, trees]) => {
            // Build org name lookup from trees
            const orgNames = {};
            function walkTree(t) {
                orgNames[t.node.org_id] = t.node.name;
                t.children.forEach(walkTree);
            }
            trees.forEach(walkTree);

            const currentUser = getCurrentUser();
            const listEl = modal.querySelector('.seerai-switcher-list');
            const searchEl = modal.querySelector('.seerai-switcher-search');

            function renderList(filter) {
                const filtered = filter
                    ? users.filter(u => u.user_id.toLowerCase().includes(filter.toLowerCase()))
                    : users;

                // Group by org
                const groups = {};
                for (const u of filtered) {
                    const orgName = orgNames[u.org_id] || u.org_id || 'Unassigned';
                    if (!groups[orgName]) groups[orgName] = [];
                    groups[orgName].push(u);
                }

                if (!filtered.length) {
                    listEl.innerHTML = '<div style="padding:1rem;color:#666;text-align:center;">No matches</div>';
                    return;
                }

                let html = '';
                for (const [group, groupUsers] of Object.entries(groups)) {
                    html += `<div class="seerai-switcher-group">${esc(group)}</div>`;
                    for (const u of groupUsers) {
                        const isCurrent = currentUser && currentUser.user_id === u.user_id;
                        const badge = u.role === 'exec'
                            ? '<span class="role-badge role-exec" style="font-size:0.65rem;margin-left:0.4rem;">exec</span>'
                            : '';
                        html += `<div class="seerai-switcher-item ${isCurrent ? 'current' : ''}" data-uid="${esc(u.user_id)}" data-role="${u.role}" data-org="${esc(u.org_id || '')}">
                            <span class="name">${esc(u.user_id)}${badge}</span>
                            ${isCurrent ? '<span class="meta">current</span>' : ''}
                        </div>`;
                    }
                }
                listEl.innerHTML = html;

                listEl.querySelectorAll('.seerai-switcher-item').forEach(item => {
                    item.addEventListener('click', () => {
                        const selected = {
                            user_id: item.dataset.uid,
                            role: item.dataset.role,
                            org_id: item.dataset.org || null,
                        };
                        setCurrentUser(selected);
                        overlay.remove();
                        // Navigate to appropriate home
                        if (selected.role === 'exec') {
                            window.location.href = '/exec';
                        } else {
                            window.location.href = `/my/${encodeURIComponent(selected.user_id)}`;
                        }
                    });
                });
            }

            renderList('');
            searchEl.addEventListener('input', () => renderList(searchEl.value));
            searchEl.focus();
        });

        // Close on Escape
        const onKey = (e) => { if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', onKey); } };
        document.addEventListener('keydown', onKey);
    }

    // Auto-open switcher if no user selected
    renderNav();
    if (!getCurrentUser()) {
        openSwitcher();
    }
})();
