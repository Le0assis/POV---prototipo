/**
 * Configuração central do frontend POV.
 * A URL da API só existe neste arquivo.
 */

const LOCAL_HOSTS = ['localhost', '127.0.0.1', '[::1]', '::1'];
const API_URL_OVERRIDE_KEY = 'pov_api_url';
const API_URL_LOCAL = 'http://127.0.0.1:8000';
const API_URL_REMOTE = 'https://api.pov-unimar.com';

function resolveApiBaseUrl() {
    if (typeof window === 'undefined') return API_URL_LOCAL;

    try {
        const override = window.localStorage.getItem(API_URL_OVERRIDE_KEY);
        if (override && override.trim()) {
            return override.trim().replace(/\/+$/, '');
        }
    } catch (_) {
        // localStorage indisponível (modo privado, etc.): segue para a detecção automática.
    }

    const host = window.location.hostname;
    return LOCAL_HOSTS.includes(host) ? API_URL_LOCAL : API_URL_REMOTE;
}

export const API_BASE_URL = resolveApiBaseUrl();

export const STEP_LENGTH_DEFAULT = 0.70;
export const WEINBERG_K = 0.45;
export const STEP_MIN_M = 0.40;
export const STEP_MAX_M = 0.95;
export const POLL_MS = 500;
export const ANGLE_TOLERANCE_DEG = 30;

export const STORAGE_KEYS = Object.freeze({
    stepLength: 'pov_step_length',
    headingOffset: 'pov_heading_offset',
    startPoint: 'pov_start_point'
});
