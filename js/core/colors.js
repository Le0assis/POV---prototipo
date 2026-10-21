/**
 * Cores de polilinha e marcador. Os valores moram em tokens.css;
 * o canvas e o Leaflet leem a cor já resolvida.
 */

const SENTINEL = 'rgb(1, 2, 3)';

export const MAP_COLOR_TOKENS = Object.freeze({
    recorded: ['--path-recorded', '#22d3ee'],
    manual: ['--path-manual', '#64748b'],
    previewBg: ['--path-preview-bg', 'rgba(6, 10, 20, 0.65)'],
    previewMuted: ['--path-preview-muted', '#94a3b8'],
    previewStroke: ['--path-preview-stroke', '#22d3ee'],
    pathStart: ['--path-start', '#22c55e'],
    pathEnd: ['--path-end', '#8b5cf6'],
    sparkline: ['--sparkline', '#22d3ee']
});

const cache = new Map();

function readCustomProperty(name) {
    if (typeof document === 'undefined' || typeof getComputedStyle !== 'function') return '';
    const probe = document.createElement('span');
    probe.setAttribute('aria-hidden', 'true');
    probe.style.position = 'absolute';
    probe.style.left = '0';
    probe.style.top = '0';
    probe.style.pointerEvents = 'none';
    probe.style.color = SENTINEL;
    probe.style.color = `var(${name})`;
    const parent = document.body || document.documentElement;
    parent.appendChild(probe);
    const resolved = getComputedStyle(probe).color;
    probe.remove();
    if (!resolved || resolved === SENTINEL) return '';
    return resolved;
}

/** Cor computada do token. Sem DOM, devolve o fallback. */
export function tokenColor(key) {
    const pair = MAP_COLOR_TOKENS[key];
    if (!pair) return '';
    const [name, fallback] = pair;
    if (cache.has(name)) return cache.get(name);
    const resolved = readCustomProperty(name);
    if (!resolved) return fallback;
    cache.set(name, resolved);
    return resolved;
}

export function mapLineColors() {
    return {
        recorded: tokenColor('recorded'),
        manual: tokenColor('manual')
    };
}

export function pathPreviewColors() {
    return {
        background: tokenColor('previewBg'),
        muted: tokenColor('previewMuted'),
        stroke: tokenColor('previewStroke'),
        start: tokenColor('pathStart'),
        end: tokenColor('pathEnd')
    };
}

export function sparklineColor() {
    return tokenColor('sparkline');
}
