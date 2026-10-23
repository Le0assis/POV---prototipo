/**
 * Preferências de acessibilidade do visitante.
 * A mesma chave é lida pelo script inline do <head>, antes da primeira pintura.
 */

export const A11Y_STORAGE_KEY = 'pov.a11y';

export const DEFAULT_A11Y = Object.freeze({
    hc: false,
    fontLg: false,
    speech: false
});

export function emptyA11yPrefs() {
    return { hc: false, fontLg: false, speech: false };
}

export function readA11yPrefs(storage = undefined) {
    const bag = storage || defaultStorage();
    if (!bag) return emptyA11yPrefs();
    try {
        const raw = bag.getItem(A11Y_STORAGE_KEY);
        if (!raw) return emptyA11yPrefs();
        const data = JSON.parse(raw);
        return {
            hc: Boolean(data && data.hc),
            fontLg: Boolean(data && data.fontLg),
            speech: Boolean(data && data.speech)
        };
    } catch (_) {
        return emptyA11yPrefs();
    }
}

export function saveA11yPrefs(prefs, storage = undefined) {
    const bag = storage || defaultStorage();
    const next = {
        hc: Boolean(prefs && prefs.hc),
        fontLg: Boolean(prefs && prefs.fontLg),
        speech: Boolean(prefs && prefs.speech)
    };
    if (bag) bag.setItem(A11Y_STORAGE_KEY, JSON.stringify(next));
    return next;
}

/** Liga `html.hc` e `html.font-lg` sem esperar o restante da página. */
export function applyA11yClasses(root, prefs) {
    if (!root || !root.classList) return;
    const next = prefs || emptyA11yPrefs();
    root.classList.toggle('hc', Boolean(next.hc));
    root.classList.toggle('font-lg', Boolean(next.fontLg));
}

function defaultStorage() {
    try {
        if (typeof localStorage === 'undefined') return null;
        return localStorage;
    } catch (_) {
        return null;
    }
}
