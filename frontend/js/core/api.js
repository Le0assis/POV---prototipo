/**
 * Camada HTTP única do frontend POV.
 * Toda chamada ao backend passa por aqui.
 *
 * Escritas protegidas enviam `X-Editor-Password` (sessionStorage, mesma chave
 * no editor, no gravador e nas rotas). Inclui process-raw, checkpoints, edges,
 * posição, map-config, POST/DELETE /api/routes e POST /api/reset.
 * 401 pede a senha de novo e tenta outra vez. 503 avisa que a senha não está
 * configurada no servidor. Leitura (viewer, locate) não pede senha.
 * A entrada na administração confere a senha com GET /api/auth/check.
 */

import { API_BASE_URL } from './config.js';

const EDITOR_PASSWORD_KEY = 'pov_editor_password';

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
            .map(item => {
                if (!item || typeof item !== 'object') return String(item);
                const loc = Array.isArray(item.loc)
                    ? item.loc.filter(part => part !== 'body').join('.')
                    : '';
                const msg = item.msg || '';
                return loc && msg ? `${loc}: ${msg}` : (msg || loc);
            })
            .filter(Boolean);
        return msgs.length ? msgs.join('; ') : fallback;
    }
    try {
        return JSON.stringify(detail);
    } catch (_) {
        return fallback;
    }
}

async function request(path, { method = 'GET', body, query, timeout = 8000, password } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);

    const headers = { 'Content-Type': 'application/json' };
    if (password) headers['X-Editor-Password'] = password;

    const options = {
        method,
        headers,
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

export function getEditorPassword() {
    try {
        return sessionStorage.getItem(EDITOR_PASSWORD_KEY) || '';
    } catch (_) {
        return '';
    }
}

export function setEditorPassword(value) {
    try {
        sessionStorage.setItem(EDITOR_PASSWORD_KEY, value);
    } catch (_) {
        /* sessionStorage indisponível: a senha vale só nesta chamada */
    }
}

export function clearEditorPassword() {
    try {
        sessionStorage.removeItem(EDITOR_PASSWORD_KEY);
    } catch (_) {
        /* ignora */
    }
}

/**
 * Confere a senha com GET /api/auth/check e o header X-Editor-Password.
 * 204: senha válida. 401: ausente ou errada. 503: servidor sem senha.
 * 401 e 503 limpam a sessão.
 */
export async function verifyEditorPassword(password) {
    const given = password || getEditorPassword();
    if (!given) throw new ApiError('Senha do editor necessária.', 401);
    try {
        await request('/api/auth/check', { method: 'GET', password: given });
    } catch (err) {
        if (err.status === 503) {
            clearEditorPassword();
            throw new ApiError('A senha do editor não está configurada no servidor.', 503);
        }
        if (err.status === 401) {
            clearEditorPassword();
            throw new ApiError('Senha incorreta.', 401);
        }
        throw err;
    }
    return true;
}

let pendingPrompt = null;

/**
 * Garante a senha do editor na sessionStorage.
 * Editor e gravador usam este mesmo prompt e a mesma chave.
 * @returns {Promise<string|null>} senha, ou null se o usuário cancelar
 */
export function ensureEditorPassword({ force = false, message = '' } = {}) {
    if (!force) {
        const existing = getEditorPassword();
        if (existing) return Promise.resolve(existing);
    }
    if (pendingPrompt) return pendingPrompt;
    pendingPrompt = promptEditorPassword(message).finally(() => {
        pendingPrompt = null;
    });
    return pendingPrompt;
}

/**
 * Escrita protegida: envia a senha, e em 401 pede de novo e tenta uma vez.
 * Em 503 não insiste.
 */
async function editorWrite(path, options) {
    let password = await ensureEditorPassword();
    if (!password) throw new ApiError('Senha do editor necessária.', 401);
    try {
        return await request(path, { ...options, password });
    } catch (err) {
        if (err.status === 503) {
            throw new ApiError('A senha do editor não está configurada no servidor.', 503);
        }
        if (err.status !== 401) throw err;
        clearEditorPassword();
        password = await ensureEditorPassword({
            force: true,
            message: 'Senha incorreta. Digite de novo.'
        });
        if (!password) throw new ApiError('Senha incorreta.', 401);
        try {
            return await request(path, { ...options, password });
        } catch (retryErr) {
            if (retryErr.status === 503) {
                throw new ApiError('A senha do editor não está configurada no servidor.', 503);
            }
            if (retryErr.status === 401) {
                clearEditorPassword();
                throw new ApiError('Senha incorreta.', 401);
            }
            throw retryErr;
        }
    }
}

function promptEditorPassword(message) {
    return new Promise((resolve) => {
        const previous = document.activeElement;
        const overlay = document.createElement('div');
        overlay.className = 'modal';

        const content = document.createElement('form');
        content.className = 'modal-content';
        content.setAttribute('role', 'dialog');
        content.setAttribute('aria-modal', 'true');
        content.setAttribute('aria-labelledby', 'editor-password-title');

        const title = document.createElement('h2');
        title.id = 'editor-password-title';
        title.textContent = 'Senha do editor';

        const hint = document.createElement('p');
        hint.className = 'hint';
        hint.textContent = message
            || 'Vale para a administração, só nesta aba.';
        if (message) hint.setAttribute('role', 'alert');

        const label = document.createElement('label');
        label.className = 'form-group';
        label.textContent = 'Senha';
        const input = document.createElement('input');
        input.type = 'password';
        input.autocomplete = 'current-password';
        input.required = true;
        label.appendChild(input);

        const actions = document.createElement('div');
        actions.className = 'form-actions';

        const cancel = document.createElement('button');
        cancel.type = 'button';
        cancel.className = 'btn btn-ghost';
        cancel.textContent = 'Cancelar';

        const ok = document.createElement('button');
        ok.type = 'submit';
        ok.className = 'btn btn-primary';
        ok.textContent = 'Entrar';

        actions.append(cancel, ok);
        content.append(title, hint, label, actions);
        overlay.appendChild(content);

        let settled = false;
        let onKey = null;
        const close = (value) => {
            if (settled) return;
            settled = true;
            if (onKey) document.removeEventListener('keydown', onKey);
            overlay.remove();
            if (previous && typeof previous.focus === 'function') previous.focus();
            resolve(value);
        };

        onKey = (event) => {
            if (event.key === 'Escape') {
                event.preventDefault();
                close(null);
            }
        };

        content.addEventListener('submit', (event) => {
            event.preventDefault();
            const value = input.value;
            if (!value) return;
            setEditorPassword(value);
            close(value);
        });
        cancel.addEventListener('click', () => close(null));
        overlay.addEventListener('click', (event) => {
            if (event.target === overlay) close(null);
        });
        document.addEventListener('keydown', onKey);

        document.body.appendChild(overlay);
        input.focus();
    });
}

export function getMap() {
    return request('/api/map');
}

export function getCategories() {
    return request('/api/categories');
}

export function getRoutes() {
    return request('/api/routes');
}

export function getRoute(id) {
    return request(`/api/routes/${encodeURIComponent(id)}`);
}

export function createRoute({ start_node, end_node, name }) {
    return editorWrite('/api/routes', {
        method: 'POST',
        body: { start_node, end_node, name }
    });
}

export function deleteRoute(id) {
    return editorWrite(`/api/routes/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export function getCompassRoute(start, end) {
    return request('/api/compass_route', { query: { start, end } });
}

export function reset(startNode) {
    return editorWrite('/api/reset', {
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
    return editorWrite('/api/checkpoints', {
        method: 'POST',
        body: { name }
    });
}

export function saveEdge({ source, target, distance_m, heading_rad }) {
    return editorWrite('/api/edges', {
        method: 'POST',
        body: { source, target, distance_m, heading_rad }
    });
}

export function processRaw({ source, target, samples }) {
    return editorWrite('/api/edges/process-raw', {
        method: 'POST',
        body: { source, target, samples },
        timeout: 30000
    });
}

export function getConnections({ includePath = true } = {}) {
    return request('/api/connections', {
        query: { include_path: includePath }
    });
}

export function getConnection(edgeId) {
    return request(`/api/connections/${encodeURIComponent(edgeId)}`);
}

export function getPdrConfig() {
    return request('/api/pdr/config');
}

export function updateCheckpointPosition(name, { pos_x_px, pos_y_px }) {
    return editorWrite(`/api/checkpoints/${encodeURIComponent(name)}/position`, {
        method: 'PATCH',
        body: { pos_x_px, pos_y_px }
    });
}

export function getMapConfig() {
    return request('/api/map-config');
}

export function saveMapConfig({ plan_image, px_per_m, rotation_rad }) {
    return editorWrite('/api/map-config', {
        method: 'PUT',
        body: { plan_image, px_per_m, rotation_rad }
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
