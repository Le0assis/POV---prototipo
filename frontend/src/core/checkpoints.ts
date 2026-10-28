/**
 * Um só lugar para a identidade do checkpoint no contrato M03.
 * A leitura pública traz `slug`, `building_id` e `category`.
 * Sem slug, a chave cai no nome. GET /api/categories e
 * GET /api/checkpoints/resolve?b=&cp= (404 quando não existe)
 * passam por aqui antes de chegar na tela.
 */

import { resolveCheckpoint as requestResolveCheckpoint } from './api.js';

export const RESOLVE_UNRECOGNIZED = 'QR não reconhecido neste prédio';
export const RESOLVE_RETRY = 'Tentar de novo';
export const RESOLVE_FALLBACK_WARNING = 'GET /api/checkpoints/resolve indisponível; usando a lista de checkpoints já carregada.';

export function checkpointSlug(raw) {
    if (!raw) return '';
    if (typeof raw === 'string') return raw.trim();
    const slug = raw.slug == null ? '' : String(raw.slug).trim();
    if (slug) return slug;
    return String(raw.name || raw.id || raw.label || '').trim();
}

function categoryOf(value) {
    if (!value) return null;
    if (typeof value === 'string') {
        const code = value.trim();
        return code ? { code, label: code } : null;
    }
    if (typeof value !== 'object') return null;
    const code = value.code == null ? '' : String(value.code).trim();
    if (!code) return null;
    const labelSource = value.label != null ? value.label : value.name;
    const label = labelSource == null ? code : String(labelSource).trim();
    const category: any = { code, label: label || code };
    const icon = value.icon == null ? '' : String(value.icon).trim();
    if (icon) category.icon = icon;
    return category;
}

function buildingIdOf(value) {
    if (value == null || value === '') return null;
    const id = Number(value);
    return Number.isFinite(id) ? id : null;
}

/** Normaliza um checkpoint. `null` se não houver slug nem nome. */
export function adaptCheckpoint(raw) {
    if (!raw || typeof raw !== 'object') return null;
    const slug = checkpointSlug(raw);
    if (!slug) return null;
    const name = String(raw.name || raw.id || raw.label || slug).trim() || slug;
    return {
        ...raw,
        name,
        slug,
        building_id: buildingIdOf(raw.building_id),
        category: categoryOf(raw.category)
    };
}

export function adaptCheckpoints(list) {
    return (Array.isArray(list) ? list : [])
        .map((item) => adaptCheckpoint(item))
        .filter(Boolean);
}

/** Corpo de GET /api/categories: `{ categories: [...] }` ou a lista. */
export function adaptCategories(payload) {
    const rows = Array.isArray(payload)
        ? payload
        : (payload && Array.isArray(payload.categories) ? payload.categories : []);
    return rows.map((row) => {
        const code = row && row.code != null ? String(row.code).trim() : '';
        if (!code) return null;
        const labelSource = row.label != null ? row.label : row.name;
        const label = labelSource == null ? code : String(labelSource).trim();
        const orderSource = row.sort_order != null ? row.sort_order : row.order;
        const order = Number(orderSource);
        const category: any = {
            code,
            label: label || code,
            sort_order: Number.isFinite(order) ? order : null
        };
        const icon = row.icon == null ? '' : String(row.icon).trim();
        if (icon) category.icon = icon;
        return category;
    }).filter(Boolean);
}

/** Corpo de GET /api/checkpoints/resolve: `{ checkpoint }` ou o próprio objeto. */
export function adaptResolve(payload) {
    if (!payload || typeof payload !== 'object') return null;
    const raw = payload.checkpoint && typeof payload.checkpoint === 'object'
        ? payload.checkpoint
        : payload;
    return adaptCheckpoint(raw);
}

/** 404 de /api/checkpoints/resolve: o QR não aponta para um checkpoint. */
export function isResolveNotFound(error) {
    return Boolean(error && Number(error.status) === 404);
}

/**
 * 405, ou 404 que não é o "checkpoint não encontrado" do contrato:
 * a rota ainda não existe neste servidor.
 */
export function isResolveEndpointMissing(error) {
    if (!error) return false;
    const status = Number(error.status);
    if (status === 405) return true;
    if (status !== 404) return false;
    const detail = String(error.detail || error.message || '').toLowerCase();
    if (detail.includes('checkpoint não encontrado') || detail.includes('checkpoint nao encontrado')) {
        return false;
    }
    return true;
}

export class CheckpointResolveError extends Error {
    code: any;

    constructor(code, message) {
        super(message);
        this.name = 'CheckpointResolveError';
        this.code = code;
    }
}

function notFoundError() {
    return new CheckpointResolveError('not-found', RESOLVE_UNRECOGNIZED);
}

function networkError(cause) {
    const error = new CheckpointResolveError('network', RESOLVE_RETRY);
    if (cause) error.cause = cause;
    return error;
}

/** Mesma chave do backend: pontas, espaços internos e caixa. Acento fica. */
export function checkpointNameKey(value) {
    return String(value == null ? '' : value)
        .trim()
        .split(/\s+/)
        .filter(Boolean)
        .join(' ')
        .toLocaleLowerCase('pt-BR');
}

function sameCheckpoint(item, wanted) {
    if (!item || !wanted) return false;
    const text = String(wanted).trim();
    const slug = item.slug == null ? '' : String(item.slug);
    if (slug && slug === text) return true;
    const key = checkpointNameKey(text);
    return Boolean(key) && checkpointNameKey(item.name) === key;
}

/** Procura o slug na lista já carregada. Com `b`, respeita o prédio quando ele vier no item. */
export function findLoadedCheckpoint(list, slug, buildingId) {
    const wanted = slug == null ? '' : String(slug).trim();
    if (!wanted) return null;
    const rows = (Array.isArray(list) ? list : []).filter((item) => sameCheckpoint(item, wanted));
    if (buildingId == null || buildingId === '') return adaptCheckpoint(rows[0]);
    const building = Number(buildingId);
    const inBuilding = rows.find((item) => item.building_id == null || Number(item.building_id) === building);
    return adaptCheckpoint(inBuilding);
}

/**
 * Resolve o QR no contrato público.
 * 200 → checkpoint adaptado.
 * 404 do checkpoint → erro `not-found` ("QR não reconhecido neste prédio").
 * Falha de rede → erro `network` ("Tentar de novo").
 * 404 da rota ou 405 → aviso e busca do slug na lista já carregada.
 * Sem `b` (digitação manual) a rota exige o prédio; cai na mesma lista.
 */
export async function resolveScannedCheckpoint({
    b,
    cp,
    checkpoints = null,
    loadCheckpoints,
    request = requestResolveCheckpoint,
    warn = (message) => console.warn(message)
} = {} as any) {
    const slug = cp == null ? '' : String(cp).trim();
    if (!slug) throw notFoundError();

    async function fromList(buildingId) {
        let list = Array.isArray(checkpoints) ? checkpoints : null;
        if (list == null && typeof loadCheckpoints === 'function') {
            list = await loadCheckpoints();
        }
        const found = findLoadedCheckpoint(list, slug, buildingId);
        if (!found) throw notFoundError();
        return found;
    }

    if (b == null || b === '') return fromList(null);

    try {
        const payload = await request({ b, cp: slug });
        const found = adaptResolve(payload);
        if (!found) throw notFoundError();
        return found;
    } catch (err) {
        if (err instanceof CheckpointResolveError) throw err;
        if (isResolveEndpointMissing(err) || Number(err && err.status) === 422) {
            if (isResolveEndpointMissing(err) && typeof warn === 'function') warn(RESOLVE_FALLBACK_WARNING);
            return fromList(b);
        }
        if (Number(err && err.status) === 404) throw notFoundError();
        throw networkError(err);
    }
}
