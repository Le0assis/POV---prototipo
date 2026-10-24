/**
 * Seletor Visitante | Admin e a porta da área /admin/.
 * A senha continua em sessionStorage (api.js). Quem já tem senha nesta aba entra.
 * Quem digita uma senha nova passa por uma chamada protegida leve antes de seguir.
 */

import { SHOW_ROLE_TOGGLE } from './config.js';
import {
    clearEditorPassword,
    describeEditor503,
    ensureEditorPassword,
    getEditorPassword,
    PASSWORD_UNCONFIGURED_MESSAGE,
    verifyEditorPassword
} from './api.js';
import { toast } from './toast.js';

export { PASSWORD_UNCONFIGURED_MESSAGE };
export const PASSWORD_WRONG_MESSAGE = 'Senha incorreta. Digite de novo.';
export const PASSWORD_UNREACHABLE_MESSAGE = 'Não foi possível validar a senha.';

const VISITOR_PAGE = 'index.html';
const ADMIN_PAGE = 'index.html';

let gatePromise = null;
let adminGranted = false;
const grantedListeners = [];

export function isAdminPath(pathname) {
    return /\/admin(?:\/|$)/.test(pathname || '');
}

export function currentRole(pathname) {
    return isAdminPath(pathname) ? 'admin' : 'visitor';
}

export function visitorHref(pathname) {
    return (isAdminPath(pathname) ? '../' : '') + VISITOR_PAGE;
}

export function adminIndexHref(pathname) {
    return (isAdminPath(pathname) ? '' : 'admin/') + ADMIN_PAGE;
}

export function adminFooterHref(pathname) {
    return isAdminPath(pathname) ? 'index.html' : 'admin/index.html';
}

/** Mantém a query e o hash (T3 leva origem/destino no hash). */
export function hrefForRole(role, { pathname = '', hash = '', search = '' } = {} as any) {
    const base = role === 'admin' ? adminIndexHref(pathname) : visitorHref(pathname);
    return base + (search || '') + (hash || '');
}

export function chromePlan(showToggle) {
    return {
        showToggle: Boolean(showToggle),
        showBadge: true,
        footerLabel: showToggle ? '' : 'Administração'
    };
}

/** Próximo índice do radiogroup. null se a tecla não muda a seleção. */
export function nextRadioIndex(current, key, length = 2) {
    const index = Number(current) || 0;
    if (key === 'ArrowRight' || key === 'ArrowDown') return (index + 1) % length;
    if (key === 'ArrowLeft' || key === 'ArrowUp') return (index - 1 + length) % length;
    if (key === 'Home') return 0;
    if (key === 'End') return length - 1;
    return null;
}

async function probeStatus(verify, password) {
    try {
        await verify(password);
        return { status: 200, error: null };
    } catch (err) {
        const status = err && typeof err.status === 'number' ? err.status : 0;
        return { status, error: err };
    }
}

function badCredentials(status) {
    return status === 401 || status === 403;
}

/**
 * Decide a entrada em Admin.
 * Senha já na sessão: segue, sem modal.
 * Sem senha: pede, valida, e em 401/403 pede outra vez. A segunda falha fica na página.
 * 503 não apaga a senha: ou o hash não existe, ou o servidor está ocupado.
 */
export async function requestAdminEntry({
    getPassword,
    prompt,
    verify,
    clearPassword = clearEditorPassword,
    showToggle = SHOW_ROLE_TOGGLE
} = {} as any) {
    if (showToggle === false) return { action: 'ignore' };

    const stored = typeof getPassword === 'function' ? getPassword() : '';
    if (stored) return { action: 'navigate' };

    let password = await prompt('');
    if (!password) return { action: 'cancel' };

    let result = await probeStatus(verify, password);
    if (badCredentials(result.status)) {
        clearPassword();
        password = await prompt(PASSWORD_WRONG_MESSAGE);
        if (!password) return { action: 'cancel' };
        result = await probeStatus(verify, password);
    }
    if (badCredentials(result.status)) {
        clearPassword();
        return { action: 'stay', error: PASSWORD_WRONG_MESSAGE };
    }
    if (result.status === 503) {
        return { action: 'warn', message: describeEditor503(result.error).message };
    }
    if (result.status !== 200) {
        return { action: 'stay', error: PASSWORD_UNREACHABLE_MESSAGE };
    }
    return { action: 'navigate' };
}

function locationBits() {
    return {
        pathname: window.location.pathname,
        hash: window.location.hash,
        search: window.location.search
    };
}

function go(href, { replace = false } = {} as any) {
    const next = new URL(href, window.location.href);
    const here = new URL(window.location.href);
    if (next.pathname === here.pathname && next.search === here.search && next.hash === here.hash) {
        return;
    }
    if (replace) window.location.replace(next.href);
    else window.location.assign(next.href);
}

export function whenAdminGranted(listener) {
    if (typeof listener !== 'function') return;
    if (adminGranted) {
        listener();
        return;
    }
    grantedListeners.push(listener);
}

function notifyGranted() {
    adminGranted = true;
    grantedListeners.splice(0).forEach((listener) => listener());
}

function showGateMessage(message, { retry = false } = {} as any) {
    let box = document.getElementById('admin-gate-message');
    if (!box) {
        box = document.createElement('section');
        box.id = 'admin-gate-message';
        box.className = 'card admin-gate';
        box.setAttribute('role', 'alert');
        const header = document.getElementById('admin-header');
        if (header && header.parentNode) header.after(box);
        else document.body.append(box);
    }
    box.replaceChildren();
    const text = document.createElement('p');
    text.textContent = message;
    box.append(text);
    if (retry) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-primary';
        button.textContent = 'Informar senha';
        button.addEventListener('click', () => {
            box.remove();
            requireAdminAccess();
        });
        box.append(button);
    }
}

function promptForAdmin(message) {
    return ensureEditorPassword({ force: true, message: message || '' });
}

export function requireAdminAccess() {
    if (adminGranted) return Promise.resolve(true);
    if (!gatePromise) {
        gatePromise = runGate().finally(() => {
            gatePromise = null;
        });
    }
    return gatePromise;
}

async function runGate() {
    const decision = await requestAdminEntry({
        getPassword: getEditorPassword,
        prompt: promptForAdmin,
        verify: verifyEditorPassword,
        showToggle: true
    });
    if (decision.action === 'navigate') {
        notifyGranted();
        return true;
    }
    if (decision.action === 'cancel') {
        go(hrefForRole('visitor', locationBits()), { replace: true });
        return false;
    }
    const text = decision.message || decision.error || PASSWORD_UNREACHABLE_MESSAGE;
    showGateMessage(text, { retry: true });
    toast(text, decision.action === 'warn' ? 'warn' : 'erro', 8000);
    return false;
}

export async function enterAdminFromToggle() {
    const decision = await requestAdminEntry({
        getPassword: getEditorPassword,
        prompt: promptForAdmin,
        verify: verifyEditorPassword
    });
    if (decision.action === 'navigate') {
        go(hrefForRole('admin', locationBits()));
        return decision;
    }
    if (decision.action === 'warn' || decision.action === 'stay') {
        toast(decision.message || decision.error, decision.action === 'warn' ? 'warn' : 'erro', 8000);
    }
    return decision;
}

function paintRole(buttons, role) {
    buttons.forEach((button) => {
        const on = button.dataset.role === role;
        button.classList.toggle('is-active', on);
        button.setAttribute('aria-checked', on ? 'true' : 'false');
        button.tabIndex = on ? 0 : -1;
    });
}

export function mountRoleChrome() {
    if (typeof document === 'undefined') return;
    if (document.querySelector('[data-role-chrome]')) return;

    const plan = chromePlan(SHOW_ROLE_TOGGLE);
    const bar = document.createElement('div');
    bar.className = 'role-bar';
    bar.dataset.roleChrome = 'true';

    if (plan.showToggle) {
        const group = document.createElement('div');
        group.className = 'segmented';
        group.setAttribute('role', 'radiogroup');
        group.setAttribute('aria-label', 'Modo de acesso');

        const buttons = ['visitor', 'admin'].map((role) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'segmented-item';
            button.dataset.role = role;
            button.setAttribute('role', 'radio');
            button.textContent = role === 'admin' ? 'Admin' : 'Visitante';
            group.append(button);
            return button;
        });

        const select = (role) => {
            const pathRole = currentRole(window.location.pathname);
            if (role === pathRole) {
                paintRole(buttons, pathRole);
                return;
            }
            if (role === 'visitor') {
                go(hrefForRole('visitor', locationBits()));
                return;
            }
            enterAdminFromToggle().then((decision) => {
                if (!decision || decision.action !== 'navigate') paintRole(buttons, pathRole);
            });
        };

        buttons.forEach((button) => {
            button.addEventListener('click', () => select(button.dataset.role));
        });

        group.addEventListener('keydown', (event) => {
            const current = buttons.findIndex((button) => button.dataset.role === currentRole(window.location.pathname));
            const next = nextRadioIndex(current < 0 ? 0 : current, event.key, buttons.length);
            if (next == null) return;
            event.preventDefault();
            buttons[next].focus();
            select(buttons[next].dataset.role);
        });

        paintRole(buttons, currentRole(window.location.pathname));
        bar.append(group);
    }

    if (plan.showBadge) {
        const badge = document.createElement('span');
        badge.className = 'badge-homolog';
        badge.textContent = 'HOMOLOGAÇÃO';
        bar.append(badge);
    }

    if (isAdminPath(window.location.pathname)) {
        bar.classList.add('role-bar--header');
        const header = document.getElementById('admin-header') || createAdminHeader();
        header.prepend(bar);
    } else {
        const nav = document.querySelector('.top-nav, .top-bar');
        if (nav) nav.after(bar);
        else document.body.prepend(bar);
    }

    if (plan.footerLabel) {
        const footer = document.createElement('footer');
        footer.className = 'site-footer';
        const link = document.createElement('a');
        link.className = 'admin-link';
        link.href = adminFooterHref(window.location.pathname);
        link.textContent = plan.footerLabel;
        footer.append(link);
        document.body.append(footer);
    }
}

function createAdminHeader() {
    const header = document.createElement('header');
    header.id = 'admin-header';
    header.className = 'admin-header';
    const nav = document.querySelector('.top-nav, .top-bar');
    if (nav) nav.after(header);
    else document.body.prepend(header);
    return header;
}
