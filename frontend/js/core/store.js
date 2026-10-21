/**
 * Sessão do visitante: { origin, destination, state } em sessionStorage,
 * com origem e destino espelhados no hash `#origem=<slug>&destino=<slug>`.
 */

export const SESSION_KEY = 'pov.visitor.session';

export const VISITOR_STATES = Object.freeze([
    'E0',
    'E1',
    'E2',
    'E3',
    'E4',
    'E5',
    'ERRO_CAMERA',
    'ERRO_ROTA',
    'ERRO_MAPA',
    'ERRO_REDE'
]);

const STATE_SET = new Set(VISITOR_STATES);

export function emptySession() {
    return { origin: null, destination: null, state: 'E0' };
}

export function slugOf(value) {
    if (!value) return '';
    if (typeof value === 'string') return value.trim();
    return String(value.slug || '').trim();
}

export function pointFrom(value) {
    if (!value) return null;
    if (typeof value === 'string') {
        const slug = value.trim();
        return slug ? { slug, label: slug } : null;
    }
    if (typeof value !== 'object') return null;
    const slug = slugOf(value);
    if (!slug) return null;
    const label = String(value.label || value.name || slug).trim() || slug;
    return { slug, label };
}

function stateOf(value) {
    return STATE_SET.has(value) ? value : 'E0';
}

export function normalizeSession(raw) {
    const source = raw && typeof raw === 'object' ? raw : {};
    return {
        origin: pointFrom(source.origin),
        destination: pointFrom(source.destination),
        state: stateOf(source.state)
    };
}

/** O que vai para o sessionStorage. Sem campos extras da máquina. */
export function toStored(session) {
    const normalized = normalizeSession(session);
    return {
        origin: normalized.origin,
        destination: normalized.destination,
        state: normalized.state
    };
}

export function loadSession(storage) {
    const bag = storage || defaultStorage();
    if (!bag) return emptySession();
    try {
        const raw = bag.getItem(SESSION_KEY);
        if (!raw) return emptySession();
        return normalizeSession(JSON.parse(raw));
    } catch (_) {
        return emptySession();
    }
}

export function saveSession(session, storage) {
    const bag = storage || defaultStorage();
    if (!bag) return;
    bag.setItem(SESSION_KEY, JSON.stringify(toStored(session)));
}

function emptyToNull(value) {
    if (value == null) return null;
    const text = String(value).trim();
    return text || null;
}

function hashBody(hash) {
    return String(hash || '').replace(/^#/, '').trim();
}

export function hashHasRoute(hash) {
    const body = hashBody(hash);
    if (!body) return false;
    const params = new URLSearchParams(body);
    return params.has('origem') || params.has('destino');
}

/**
 * Lê o hash. `URLSearchParams` desfaz `%20` e trata `+` como espaço,
 * então o slug volta inteiro numa única decodificação.
 */
export function parseHash(hash) {
    const body = hashBody(hash);
    if (!body) return { origin: null, destination: null };
    const params = new URLSearchParams(body);
    return {
        origin: params.has('origem') ? emptyToNull(params.get('origem')) : null,
        destination: params.has('destino') ? emptyToNull(params.get('destino')) : null
    };
}

export function formatHash(session) {
    const parts = [];
    const origin = slugOf(session && session.origin);
    const destination = slugOf(session && session.destination);
    if (origin) parts.push(`origem=${encodeURIComponent(origin)}`);
    if (destination) parts.push(`destino=${encodeURIComponent(destination)}`);
    return parts.length ? `#${parts.join('&')}` : '';
}

function labelFor(current, slug) {
    if (!slug) return '';
    if (current && current.slug === slug && current.label) return current.label;
    return slug;
}

/**
 * Hash com origem ou destino manda nesses dois campos.
 * Hash vazio mantém o que já estava na sessão (ou no storage, na carga).
 */
export function pointsFromHash(session, hash) {
    const base = normalizeSession(session);
    const kept = {
        ...base,
        returnTo: session && session.returnTo ? session.returnTo : null
    };
    if (!hashHasRoute(hash)) return kept;
    const parsed = parseHash(hash);
    return {
        ...kept,
        origin: parsed.origin ? { slug: parsed.origin, label: labelFor(base.origin, parsed.origin) } : null,
        destination: parsed.destination
            ? { slug: parsed.destination, label: labelFor(base.destination, parsed.destination) }
            : null
    };
}

export function hydrateSession(hash, storage) {
    const stored = loadSession(storage);
    return pointsFromHash(stored, hash);
}

function defaultStorage() {
    try {
        if (typeof sessionStorage === 'undefined') return null;
        return sessionStorage;
    } catch (_) {
        return null;
    }
}
