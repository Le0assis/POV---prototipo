/**
 * Navegação superior compartilhada.
 * Links relativos à raiz do frontend, também a partir de /admin/.
 * Editor e gravador ficam só no seletor Admin.
 */

import { ping } from '../core/api.js';

const PING_INTERVAL_MS = 10000;

const LINKS = [
    { key: 'home', aliases: ['index', 'dashboard', 'nav'], href: 'index.html', label: 'Início' },
    { key: 'viewer', aliases: [], href: 'viewer.html', label: 'Mapa do prédio' },
    { key: 'locate', aliases: [], href: 'locate.html', label: 'Navegar' },
    { key: 'routes', aliases: [], href: 'routes.html', label: 'Rotas' }
];

function rootPrefix() {
    if (typeof window === 'undefined') return '';
    const path = window.location.pathname || '';
    return /\/admin(?:\/|$)/.test(path) ? '../' : '';
}

function isActive(link, active) {
    return link.key === active || link.aliases.includes(active);
}

function setStatus(dot, online) {
    dot.classList.toggle('online', online);
    dot.classList.toggle('offline', !online);
    const label = online ? 'Backend online' : 'Backend offline';
    dot.title = label;
    dot.setAttribute('aria-label', label);
}

export function renderTopNav(active) {
    const nav = document.createElement('nav');
    nav.className = 'top-nav';
    nav.setAttribute('aria-label', 'Navegação principal');

    LINKS.forEach(link => {
        const a = document.createElement('a');
        a.href = rootPrefix() + link.href;
        a.className = 'nav-btn';
        a.textContent = link.label;
        if (isActive(link, active)) {
            a.classList.add('active');
            a.setAttribute('aria-current', 'page');
        }
        nav.appendChild(a);
    });

    const dot = document.createElement('span');
    dot.className = 'status-dot';
    dot.setAttribute('role', 'status');
    dot.style.alignSelf = 'center';
    dot.style.marginLeft = 'auto';
    dot.style.marginRight = '4px';
    setStatus(dot, false);

    nav.append(dot);
    return nav;
}

export function insertTopNav(active) {
    const existing = document.querySelector('.top-nav');
    if (existing) existing.remove();

    const nav = renderTopNav(active);
    document.body.insertBefore(nav, document.body.firstChild);

    const dot = nav.querySelector('.status-dot');

    const refresh = async () => {
        const online = await ping();
        setStatus(dot, online);
    };

    refresh();
    const intervalId = setInterval(refresh, PING_INTERVAL_MS);
    window.addEventListener('pagehide', () => clearInterval(intervalId), { once: true });

    return nav;
}
