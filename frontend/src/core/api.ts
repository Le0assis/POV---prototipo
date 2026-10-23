/** HTTP do frontend. Escritas protegidas enviam X-Editor-Password. */

import { API_BASE_URL } from './config.js';
import { trapTabKey } from '../ui/focus-trap.js';

const EDITOR_PASSWORD_KEY = 'pov_editor_password';

export class ApiError extends Error {
    detail: any;
    status: any;
    retryAfter: any;

    constructor(detail, status = 0, retryAfter = null) {
        super(detail);
        this.name = 'ApiError';
        this.detail = detail;
        this.status = status;
        this.retryAfter = retryAfter;
    }
}

/** Hash ausente ou hash inválido é configuração. Os outros 503 são ocupação. */
export const PASSWORD_UNCONFIGURED_MESSAGE = 'A senha do editor não está configurada no servidor.';
export const PASSWORD_MISCONFIGURED_MESSAGE = 'A senha do editor está configurada incorretamente no servidor.';
export const SERVER_BUSY_MESSAGE = 'Servidor ocupado, tente de novo em instantes';

const UNCONFIGURED_DETAIL = 'editor_password_hash não está definida';
const INVALID_HASH_DETAIL = 'não é um hash argon2id válido';

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

async function request(path, { method = 'GET', body, query, timeout = 8000, password } = {} as any) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);

    const headers = { 'Content-Type': 'application/json' };
    if (password) headers['X-Editor-Password'] = password;

    const options: any = {
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
        const retryAfter = readRetryAfter(res);
        throw new ApiError(extractDetail(data, res.status), res.status, retryAfter);
    }
    return data;
}

function readRetryAfter(res) {
    const headers = res && res.headers;
    if (!headers) return null;
    let raw = null;
    if (typeof headers.get === 'function') raw = headers.get('Retry-After');
    if ((raw == null || raw === '') && typeof headers === 'object') {
        raw = headers['Retry-After'] || headers['retry-after'] || null;
    }
    if (raw == null || raw === '') return null;
    const seconds = Number(raw);
    if (Number.isFinite(seconds) && seconds >= 0) return seconds;
    const when = Date.parse(String(raw));
    if (Number.isFinite(when)) return Math.max(0, Math.ceil((when - Date.now()) / 1000));
    return null;
}

/**
 * 503 do editor. Hash ausente: `EDITOR_PASSWORD_HASH não está definida…`.
 * Hash inválido: `EDITOR_PASSWORD_HASH não é um hash argon2id válido.`
 * Ocupado: `Retry-After` (vaga do argon2 ou pool MySQL), detalhe de ocupação,
 * ou qualquer outro 503 (MySQL fora, migração).
 */
export function describeEditor503(err) {
    const detail = String((err && (err.detail != null ? err.detail : err.message)) || '');
    const text = detail.toLowerCase();
    if (text.includes(UNCONFIGURED_DETAIL) || detail === PASSWORD_UNCONFIGURED_MESSAGE) {
        return { kind: 'unconfigured', message: PASSWORD_UNCONFIGURED_MESSAGE, retryAfter: null };
    }
    if (text.includes(INVALID_HASH_DETAIL) || detail === PASSWORD_MISCONFIGURED_MESSAGE) {
        return { kind: 'misconfigured', message: PASSWORD_MISCONFIGURED_MESSAGE, retryAfter: null };
    }
    const retryAfter = err && err.retryAfter != null ? err.retryAfter : null;
    return { kind: 'busy', message: busyMessage(retryAfter), retryAfter };
}

function busyMessage(retryAfter) {
    const seconds = Number(retryAfter);
    if (Number.isFinite(seconds) && seconds > 0) {
        return `${SERVER_BUSY_MESSAGE} (${Math.ceil(seconds)}s)`;
    }
    return SERVER_BUSY_MESSAGE;
}

function editorUnavailable(err) {
    const described = describeEditor503(err);
    return new ApiError(described.message, 503, described.retryAfter);
}

function credentialRejected(status) {
    return status === 401 || status === 403;
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
 * 204: válida. 401/403: recusada e a sessão sai. 503 não apaga a senha.
 */
export async function verifyEditorPassword(password) {
    const given = password || getEditorPassword();
    if (!given) throw new ApiError('Senha do editor necessária.', 401);
    try {
        await request('/api/auth/check', { method: 'GET', password: given });
    } catch (err) {
        if (err.status === 503) throw editorUnavailable(err);
        if (credentialRejected(err.status)) {
            clearEditorPassword();
            throw new ApiError('Senha incorreta.', err.status);
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
export function ensureEditorPassword({ force = false, message = '' } = {} as any) {
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
 * Escrita protegida: envia a senha, e em 401/403 pede de novo e tenta uma vez.
 * 503 não insiste e não apaga a senha.
 */
async function editorWrite(path, options) {
    let password = await ensureEditorPassword();
    if (!password) throw new ApiError('Senha do editor necessária.', 401);
    try {
        return await request(path, { ...options, password });
    } catch (err) {
        if (err.status === 503) throw editorUnavailable(err);
        if (!credentialRejected(err.status)) throw err;
        clearEditorPassword();
        password = await ensureEditorPassword({
            force: true,
            message: 'Senha incorreta. Digite de novo.'
        });
        if (!password) throw new ApiError('Senha incorreta.', 401);
        try {
            return await request(path, { ...options, password });
        } catch (retryErr) {
            if (retryErr.status === 503) throw editorUnavailable(retryErr);
            if (credentialRejected(retryErr.status)) {
                clearEditorPassword();
                throw new ApiError('Senha incorreta.', retryErr.status);
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
        label.setAttribute('for', 'editor-password-input');
        label.textContent = 'Senha';
        const input = document.createElement('input');
        input.id = 'editor-password-input';
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
            if (previous && typeof (previous as any).focus === 'function') (previous as any).focus();
            resolve(value);
        };

        onKey = (event) => {
            if (event.key === 'Escape') {
                event.preventDefault();
                close(null);
                return;
            }
            if (event.key === 'Tab') trapTabKey(content, event);
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

/** Leitura pública. 404 quando o slug não existe naquele prédio. */
export function resolveCheckpoint({ b, cp } = {} as any) {
    const query: any = {};
    if (b != null && b !== '') query.b = b;
    if (cp != null && cp !== '') query.cp = cp;
    return request('/api/checkpoints/resolve', { query });
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

export function getConnections({ includePath = true } = {} as any) {
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

/** Verifica se o backend responde, sem banco e sem rota de teste. */
export async function ping() {
    try {
        await request('/api/health', { timeout: 4000 });
        return true;
    } catch (_) {
        return false;
    }
}
