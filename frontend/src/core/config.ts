/** URL da API. Produção usa VITE_API_BASE_URL ou https://api.pov-unimar.com. */

const API_URL_LOCAL = 'http://127.0.0.1:8000';
const API_URL_REMOTE = 'https://api.pov-unimar.com';

function resolveApiBaseUrl() {
    const fromEnv = import.meta.env && import.meta.env.VITE_API_BASE_URL;
    if (typeof fromEnv === 'string' && fromEnv.trim()) {
        return fromEnv.trim().replace(/\/+$/, '');
    }
    if (import.meta.env && import.meta.env.PROD) return API_URL_REMOTE;
    return API_URL_LOCAL;
}

/** Rotas de teste só no dev, e só se VITE_ENABLE_TEST_ROUTES=1. No build de produção fica false. */
export const TEST_ROUTES_ENABLED = Boolean(
    import.meta.env
    && import.meta.env.DEV
    && import.meta.env.VITE_ENABLE_TEST_ROUTES === '1'
);

export const API_BASE_URL = resolveApiBaseUrl();

/** Liga o seletor Visitante | Admin. */
export const SHOW_ROLE_TOGGLE = true;

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
