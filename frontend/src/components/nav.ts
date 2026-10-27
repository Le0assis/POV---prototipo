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
    { key: 'locate', aliases: [], href: 'locate.html', label: 'Navegar' }
];

function rootPrefix() {
    if (typeof window === 'undefined') return '';
    const path = window.location.pathname || '';
    return /\/admin(?:\/|$)/.test(path) ? '../' : '';
}

function isActive(link, active) {
    return link.key === active || link.aliases.includes(active);
}

/** Destino quando não há histórico interno: menu admin ou a página inicial. */
export function previousScreenFallback() {
    const path = typeof window === 'undefined' ? '' : (window.location.pathname || '');
    if (/\/admin\/(?:index\.html)?$/.test(path)) return '../index.html';
    if (/\/admin\//.test(path)) return 'index.html';
    return rootPrefix() + 'index.html';
}

/** Volta para a tela anterior. Sem histórico do próprio site, usa o fallback. */
export function goToPreviousScreen() {
    const fallback = previousScreenFallback();
    let sameOrigin = false;
    try {
        sameOrigin = Boolean(document.referrer)
            && new URL(document.referrer).origin === window.location.origin;
    } catch (_) {
        sameOrigin = false;
    }
    if (sameOrigin && window.history.length > 1) {
        window.history.back();
        return;
    }
    window.location.assign(fallback);
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

    const back = document.createElement('button');
    back.type = 'button';
    back.className = 'nav-btn nav-back';
    back.textContent = 'Voltar';
    back.setAttribute('aria-label', 'Voltar para a tela anterior');
    back.addEventListener('click', () => goToPreviousScreen());
    nav.append(back);

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
    document.querySelectorAll('[data-pov-back]').forEach((button) => {
        button.addEventListener('click', () => goToPreviousScreen());
    });

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
