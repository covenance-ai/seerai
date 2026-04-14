/**
 * Provider and platform SVG icons.
 * Usage: providerIcon('anthropic'), platformIcon('chrome')
 * Returns an HTML string with an inline SVG, sized to fit inline text.
 */

const _PROVIDER_ICONS = {
    anthropic: `<svg viewBox="0 0 24 24" class="w-4 h-4" fill="none"><path d="M13.827 3L19.359 21h-3.178l-5.532-18h3.178zm-7.013 0h3.178l5.531 18H12.345L7.862 7.262 5.692 14h4.039l.931 3H4.452L3.54 21H.362L6.814 3z" fill="#D97706"/></svg>`,
    openai: `<svg viewBox="0 0 24 24" class="w-4 h-4"><path d="M22.282 9.821a5.985 5.985 0 00-.516-4.91 6.046 6.046 0 00-6.51-2.9A6.065 6.065 0 0011.18.316a6.047 6.047 0 00-5.765 4.22 5.985 5.985 0 00-3.996 2.9 6.046 6.046 0 00.749 7.084 5.983 5.983 0 00.516 4.911 6.047 6.047 0 006.51 2.9A6.065 6.065 0 0012.82 23.684a6.047 6.047 0 005.764-4.222 5.985 5.985 0 003.997-2.9 6.046 6.046 0 00-.749-7.084zM12.82 22.178a4.539 4.539 0 01-2.916-1.06l.145-.084 4.842-2.796a.786.786 0 00.397-.682v-6.83l2.047 1.182a.073.073 0 01.04.056v5.652a4.555 4.555 0 01-4.555 4.562zM3.955 18.065a4.531 4.531 0 01-.543-3.047l.145.087 4.842 2.796a.788.788 0 00.793 0l5.91-3.414v2.365a.073.073 0 01-.03.062L10.2 19.73a4.556 4.556 0 01-6.245-1.665zM2.648 7.907a4.538 4.538 0 012.373-1.995V11.6a.786.786 0 00.397.682l5.91 3.413-2.047 1.182a.073.073 0 01-.07.006L4.34 14.088A4.555 4.555 0 012.648 7.907zm16.524 3.847l-5.91-3.414 2.047-1.182a.073.073 0 01.07-.006l4.87 2.794a4.554 4.554 0 01-.7 8.218V12.44a.786.786 0 00-.397-.682zm2.036-3.09l-.145-.087-4.842-2.796a.788.788 0 00-.793 0l-5.91 3.414V6.83a.073.073 0 01.03-.062l4.87-2.794a4.556 4.556 0 016.79 4.69zM8.726 13.587l-2.047-1.182a.073.073 0 01-.04-.056V6.697a4.556 4.556 0 017.472-3.502l-.145.084-4.843 2.796a.786.786 0 00-.397.682zm1.112-2.396l2.634-1.521 2.634 1.521v3.042l-2.634 1.521-2.634-1.521z" fill="#10A37F"/></svg>`,
    google: `<svg viewBox="0 0 24 24" class="w-4 h-4"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>`,
    mistral: `<svg viewBox="0 0 24 24" class="w-4 h-4"><rect x="1" y="1" width="6" height="6" fill="#F7D046"/><rect x="9" y="1" width="6" height="6" fill="#000"/><rect x="17" y="1" width="6" height="6" fill="#F7D046"/><rect x="1" y="9" width="6" height="6" fill="#F2A73B"/><rect x="9" y="9" width="6" height="6" fill="#F2A73B"/><rect x="17" y="9" width="6" height="6" fill="#000"/><rect x="1" y="17" width="6" height="6" fill="#EE792F"/><rect x="9" y="17" width="6" height="6" fill="#000"/><rect x="17" y="17" width="6" height="6" fill="#EE792F"/></svg>`,
};

const _PLATFORM_ICONS = {
    chrome: `<svg viewBox="0 0 24 24" class="w-4 h-4"><circle cx="12" cy="12" r="4.5" fill="#fff" stroke="#4285F4" stroke-width="1.5"/><path d="M12 7.5a4.5 4.5 0 014.33 3.25H23.2A11.5 11.5 0 003.26 5.5l3.67 6.35A4.5 4.5 0 0112 7.5z" fill="#EA4335"/><path d="M16.33 10.75a4.5 4.5 0 01-2.17 5.42L10.5 22.5a11.5 11.5 0 0012.7-11.75h-6.87z" fill="#4285F4"/><path d="M14.16 16.17a4.5 4.5 0 01-7.23-.32L3.26 9.5A11.5 11.5 0 0010.5 22.5l3.67-6.33z" fill="#34A853"/><path d="M6.93 15.85A4.5 4.5 0 017.5 12c0-.87.25-1.68.67-2.37L4.5 3.28a11.5 11.5 0 00-1.24 6.22l3.67 6.35z" fill="#FBBC05"/></svg>`,
    firefox: `<svg viewBox="0 0 24 24" class="w-4 h-4"><circle cx="12" cy="12" r="10" fill="#FF9500"/><path d="M12 3c1.2 0 2.4.2 3.5.7-.8-.2-1.7.2-2 1-.2.8.1 1.6.7 2.3.8 1 1.1 2.4.5 3.5-.3.5-.7 1-1.2 1.3 1-.3 1.8-1.2 2-2.2.3-1.2-.1-2.5-1-3.3 2 1 3.3 3 3.5 5.2v.5c0 4.4-3.6 8-8 8s-8-3.6-8-8c0-3.3 2-6.2 5-7.5-.6.8-.8 1.8-.5 2.7.2.7.8 1.2 1.5 1.4 1.2.4 2.5-.3 2.8-1.5.2-.5.1-1-.1-1.5C11 4.7 11 3.8 11.5 3.1c.1-.1.3-.1.5-.1z" fill="#FF4500"/></svg>`,
    safari: `<svg viewBox="0 0 24 24" class="w-4 h-4"><circle cx="12" cy="12" r="10" fill="none" stroke="#006CFF" stroke-width="1.5"/><polygon points="10,14 6.5,17.5 14,10 17.5,6.5" fill="#FF3B30"/><polygon points="10,14 14,10 17.5,6.5 6.5,17.5" fill="none" stroke="#006CFF" stroke-width="0.5"/><polygon points="10,14 17.5,6.5" fill="#fff" opacity="0.4"/><line x1="12" y1="2.5" x2="12" y2="4" stroke="#006CFF" stroke-width="1"/><line x1="12" y1="20" x2="12" y2="21.5" stroke="#006CFF" stroke-width="1"/><line x1="2.5" y1="12" x2="4" y2="12" stroke="#006CFF" stroke-width="1"/><line x1="20" y1="12" x2="21.5" y2="12" stroke="#006CFF" stroke-width="1"/></svg>`,
    vscode: `<svg viewBox="0 0 24 24" class="w-4 h-4"><path d="M17.5 2L9 10.5 4.5 7l-2 1.5v7l2 1.5 4.5-3.5L17.5 22l4-2V4l-4-2zm0 3.5v13L10 12l7.5-6.5zM5 9.6l2.5 2.4L5 14.4V9.6z" fill="#007ACC"/></svg>`,
    cli: `<svg viewBox="0 0 24 24" class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="18" rx="2"/><polyline points="6,9 10,12 6,15"/><line x1="13" y1="15" x2="18" y2="15"/></svg>`,
    slack: `<svg viewBox="0 0 24 24" class="w-4 h-4"><path d="M5.042 15.165a2.528 2.528 0 01-2.52 2.523A2.528 2.528 0 010 15.165a2.527 2.527 0 012.522-2.52h2.52v2.52zm1.271 0a2.527 2.527 0 012.521-2.52 2.527 2.527 0 012.521 2.52v6.313A2.528 2.528 0 018.834 24a2.528 2.528 0 01-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 01-2.521-2.52A2.528 2.528 0 018.834 0a2.528 2.528 0 012.521 2.522v2.52H8.834zm0 1.271a2.528 2.528 0 012.521 2.521 2.528 2.528 0 01-2.521 2.521H2.522A2.528 2.528 0 010 8.834a2.528 2.528 0 012.522-2.521h6.312zM18.956 8.834a2.528 2.528 0 012.522-2.521A2.528 2.528 0 0124 8.834a2.528 2.528 0 01-2.522 2.521h-2.522V8.834zm-1.27 0a2.528 2.528 0 01-2.523 2.521 2.527 2.527 0 01-2.52-2.521V2.522A2.527 2.527 0 0115.163 0a2.528 2.528 0 012.523 2.522v6.312zM15.163 18.956a2.528 2.528 0 012.523 2.522A2.528 2.528 0 0115.163 24a2.527 2.527 0 01-2.52-2.522v-2.522h2.52zm0-1.27a2.527 2.527 0 01-2.52-2.523 2.526 2.526 0 012.52-2.52h6.315A2.528 2.528 0 0124 15.163a2.528 2.528 0 01-2.522 2.523h-6.315z" fill="#E01E5A"/></svg>`,
};

function providerIcon(name) {
    if (!name) return '';
    const svg = _PROVIDER_ICONS[name.toLowerCase()];
    if (!svg) return `<span class="inline-flex items-center justify-center w-4 h-4 rounded bg-gray-300 dark:bg-gray-600 text-[0.5rem] font-bold text-white">${name[0].toUpperCase()}</span>`;
    return svg;
}

function platformIcon(name) {
    if (!name) return '';
    const svg = _PLATFORM_ICONS[name.toLowerCase()];
    if (!svg) return `<span class="inline-flex items-center justify-center w-4 h-4 rounded bg-gray-300 dark:bg-gray-600 text-[0.5rem] font-bold text-white">${name[0].toUpperCase()}</span>`;
    return svg;
}

function providerBadge(name) {
    if (!name) return '';
    return `<span class="inline-flex items-center gap-1.5">${providerIcon(name)}<span class="text-xs text-gray-600 dark:text-gray-400">${name}</span></span>`;
}

function platformBadge(name) {
    if (!name) return '';
    return `<span class="inline-flex items-center gap-1.5">${platformIcon(name)}<span class="text-xs text-gray-600 dark:text-gray-400">${name}</span></span>`;
}

const UTILITY_COLORS = {
    useful: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
    trivial: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
    non_work: 'bg-gray-200 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
};

function utilityBadge(val) {
    if (!val) return '';
    const label = val === 'non_work' ? 'non-work' : val;
    const cls = UTILITY_COLORS[val] || UTILITY_COLORS.non_work;
    return `<span class="text-xs px-1.5 py-0.5 rounded font-medium ${cls}">${label}</span>`;
}
