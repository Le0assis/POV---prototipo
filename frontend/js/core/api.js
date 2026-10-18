/**
 * Camada HTTP única do frontend POV.
 * Toda chamada ao backend passa por aqui.
 */

import { API_BASE_URL } from './config.js';

export class ApiError extends Error {
    constructor(detail, status = 0) {
        super(detail);
        this.name = 'ApiError';
        this.detail = detail;
        this.status = status;
    }
}

function buildQueryString(query) {
    if (!query) return '';
    const params = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
            params.append(key, String(value));
        }
    });
    const qs = params.toString();
    return qs ? `?${qs}` : '';
}

function extractDetail(data, status) {
    const fallback = `Erro HTTP ${status}`;
    if (!data || data.detail === undefined || data.detail === null) return fallback;

    const { detail } = data;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
        const msgs = detail
            .map(item => (item && typeof item === 'object' ? item.msg : String(item)))
            .filter(Boolean);
        return msgs.length ? msgs.join('; ') : fallback;
    }
    try {
        return JSON.stringify(detail);
    } catch (_) {
        return fallback;
    }
}

async function request(path, { method = 'GET', body, query, timeout = 8000 } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);

    const options = {
        method,
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal
    };
    if (body !== undefined) {
        options.body = JSON.stringify(body);
    }

    let res;
    try {
        res = await fetch(`${API_BASE_URL}${path}${buildQueryString(query)}`, options);
    } catch (err) {
        if (err && err.name === 'AbortError') {
            throw new ApiError('Tempo de resposta do servidor esgotado.', 0);
        }
        throw new ApiError('Falha de conexão com o servidor.', 0);
    } finally {
        clearTimeout(timer);
    }

    let data = null;
    try {
        data = await res.json();
    } catch (_) {
        data = null;
    }

    if (!res.ok) {
        throw new ApiError(extractDetail(data, res.status), res.status);
    }
    return data;
}

export function getMap() {
    return request('/api/map');
}

export function getRoutes() {
    return request('/api/routes');
}

export function getRoute(id) {
    return request(`/api/routes/${encodeURIComponent(id)}`);
}

export function createRoute({ start_node, end_node, name }) {
    return request('/api/routes', {
        method: 'POST',
        body: { start_node, end_node, name }
    });
}

export function deleteRoute(id) {
    return request(`/api/routes/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export function getCompassRoute(start, end) {
    return request('/api/compass_route', { query: { start, end } });
}

export function reset(startNode) {
    return request('/api/reset', {
        method: 'POST',
        query: { start_node: startNode }
    });
}

export function localize(stepLengthM, yawRad) {
    return request('/api/localize', {
        method: 'POST',
        body: { step_length_m: stepLengthM, yaw_rad: yawRad }
    });
}

export function currentLocation() {
    return request('/api/current_location');
}

export function saveCheckpoint(name) {
    return request('/api/checkpoints', {
        method: 'POST',
        body: { name }
    });
}

export function saveEdge({ source, target, distance_m, heading_rad }) {
    return request('/api/edges', {
        method: 'POST',
        body: { source, target, distance_m, heading_rad }
    });
}

export function processRaw({ source, target, samples }) {
    return request('/api/edges/process-raw', {
        method: 'POST',
        body: { source, target, samples },
        timeout: 30000
    });
}

/** Verifica se o backend responde. Nunca lança: retorna true/false. */
export async function ping() {
    try {
        await request('/api/current_location', { timeout: 4000 });
        return true;
    } catch (_) {
        return false;
    }
}
