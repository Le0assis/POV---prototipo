/** URL da API. `VITE_API_URL` (ou `VITE_API_BASE_URL`) e, em produção, https://api.pov-unimar.com. */

export const API_URL_LOCAL = 'http://127.0.0.1:8000';
export const API_URL_REMOTE = 'https://api.pov-unimar.com';

function viteText(env, key) {
    const value = env && env[key];
    return typeof value === 'string' ? value.trim() : '';
}

/** `VITE_API_URL` ganha de `VITE_API_BASE_URL`. Sem as duas, produção usa o host remoto. */
export function resolveApiBaseUrl(env = import.meta.env) {
    const fromEnv = viteText(env, 'VITE_API_URL') || viteText(env, 'VITE_API_BASE_URL');
    if (fromEnv) return fromEnv.replace(/\/+$/, '');
    if (env && env.PROD) return API_URL_REMOTE;
    return API_URL_LOCAL;
}

/**
 * Localização fixa do servidor só no dev, e só com VITE_ENABLE_TEST_ROUTES=1.
 * Em produção (PROD) fica false mesmo se a variável estiver ligada.
 */
export function testRoutesEnabled(env = import.meta.env) {
    return Boolean(
        env
        && env.DEV
        && !env.PROD
        && env.VITE_ENABLE_TEST_ROUTES === '1'
    );
}

export const TEST_ROUTES_ENABLED = testRoutesEnabled();

export const API_BASE_URL = resolveApiBaseUrl();

/** Liga o seletor Visitante | Admin. */
export const SHOW_ROLE_TOGGLE = true;

export const WEINBERG_K = 0.45;
export const STEP_MIN_M = 0.40;
export const STEP_MAX_M = 0.95;

export const STORAGE_KEYS = Object.freeze({
    headingOffset: 'pov_heading_offset'
});
