import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'vitest';

import { SHOW_ROLE_TOGGLE } from '../src/core/config.ts';
import {
    PASSWORD_UNCONFIGURED_MESSAGE,
    PASSWORD_WRONG_MESSAGE,
    adminFooterHref,
    chromePlan,
    currentRole,
    hrefForRole,
    nextRadioIndex,
    requestAdminEntry
} from '../src/core/role-toggle.ts';
import {
    clearEditorPassword,
    getEditorPassword,
    setEditorPassword,
    verifyEditorPassword
} from '../src/core/api.ts';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function memoryStorage() {
    const store = new Map();
    globalThis.sessionStorage = {
        getItem: (key) => (store.has(key) ? store.get(key) : null),
        setItem: (key, value) => store.set(key, String(value)),
        removeItem: (key) => store.delete(key)
    };
}

function statusError(status) {
    const error = new Error(`HTTP ${status}`);
    error.status = status;
    return error;
}

test('com senha na sessão não abre o modal', async () => {
    let prompted = false;
    let verified = false;
    const decision = await requestAdminEntry({
        getPassword: () => 'ja-guardada',
        prompt: async () => {
            prompted = true;
            return 'outra';
        },
        verify: async () => {
            verified = true;
        },
        clearPassword: () => {}
    });
    assert.equal(decision.action, 'navigate');
    assert.equal(prompted, false);
    assert.equal(verified, false);
});

test('sem senha pede e segue quando a validação passa', async () => {
    const seen = [];
    const decision = await requestAdminEntry({
        getPassword: () => '',
        prompt: async (message) => {
            seen.push(message);
            return 'certa';
        },
        verify: async (password) => {
            assert.equal(password, 'certa');
        },
        clearPassword: () => {}
    });
    assert.equal(decision.action, 'navigate');
    assert.deepEqual(seen, ['']);
});

test('sem senha, cancelar não entra', async () => {
    let verified = false;
    const decision = await requestAdminEntry({
        getPassword: () => '',
        prompt: async () => null,
        verify: async () => {
            verified = true;
        },
        clearPassword: () => {}
    });
    assert.equal(decision.action, 'cancel');
    assert.equal(verified, false);
});

test('401 pede a senha de novo e a segunda falha fica na página', async () => {
    const prompts = [];
    let checks = 0;
    const decision = await requestAdminEntry({
        getPassword: () => '',
        prompt: async (message) => {
            prompts.push(message);
            return prompts.length === 1 ? 'primeira' : 'segunda';
        },
        verify: async () => {
            checks += 1;
            throw statusError(401);
        },
        clearPassword: () => {}
    });
    assert.equal(checks, 2);
    assert.equal(decision.action, 'stay');
    assert.equal(decision.error, PASSWORD_WRONG_MESSAGE);
    assert.equal(prompts[1], PASSWORD_WRONG_MESSAGE);
});

test('senha errada mostra erro e não navega', async () => {
    const decision = await requestAdminEntry({
        getPassword: () => '',
        prompt: async () => 'errada',
        verify: async (password) => {
            if (password !== 'certa') throw statusError(401);
        },
        clearPassword: () => {},
        showToggle: true
    });
    assert.equal(decision.action, 'stay');
    assert.match(decision.error, /Senha incorreta/);
});

test('503 avisa que a senha não está configurada no servidor', async () => {
    let cleared = false;
    const decision = await requestAdminEntry({
        getPassword: () => '',
        prompt: async () => 'qualquer',
        verify: async () => {
            throw statusError(503);
        },
        clearPassword: () => {
            cleared = true;
        }
    });
    assert.equal(decision.action, 'warn');
    assert.equal(decision.message, PASSWORD_UNCONFIGURED_MESSAGE);
    assert.equal(cleared, true);
});

test('SHOW_ROLE_TOGGLE ligado por padrão e desligado não pede senha', async () => {
    assert.equal(SHOW_ROLE_TOGGLE, true);
    const enabled = await requestAdminEntry({
        getPassword: () => 'ja-guardada',
        prompt: async () => {
            throw new Error('não devia pedir');
        },
        verify: async () => {},
        clearPassword: () => {}
    });
    assert.equal(enabled.action, 'navigate');

    let prompted = false;
    const hidden = await requestAdminEntry({
        showToggle: false,
        getPassword: () => '',
        prompt: async () => {
            prompted = true;
            return 'x';
        },
        verify: async () => {},
        clearPassword: () => {}
    });
    assert.equal(hidden.action, 'ignore');
    assert.equal(prompted, false);
    assert.equal(chromePlan(false).showToggle, false);
    assert.equal(chromePlan(false).footerLabel, 'Administração');
    assert.equal(chromePlan(true).footerLabel, '');
    assert.equal(adminFooterHref('/viewer.html'), 'admin/index.html');
});

test('a troca de papel preserva hash e query', () => {
    const bits = { pathname: '/locate.html', hash: '#origem=A&destino=B', search: '?passo=1' };
    assert.equal(hrefForRole('admin', bits), 'admin/index.html?passo=1#origem=A&destino=B');
    assert.equal(hrefForRole('visitor', bits), 'index.html?passo=1#origem=A&destino=B');
    assert.equal(
        hrefForRole('visitor', { pathname: '/admin/editor.html', hash: '#origem=A&destino=B', search: '?passo=1' }),
        '../index.html?passo=1#origem=A&destino=B'
    );
    assert.equal(currentRole('/admin/map-config.html'), 'admin');
    assert.equal(currentRole('/index.html'), 'visitor');
    assert.equal(currentRole('/viewer.html'), 'visitor');
});

test('setas, Home e End movem o radiogroup', () => {
    assert.equal(nextRadioIndex(0, 'ArrowRight'), 1);
    assert.equal(nextRadioIndex(1, 'ArrowLeft'), 0);
    assert.equal(nextRadioIndex(0, 'ArrowDown'), 1);
    assert.equal(nextRadioIndex(1, 'ArrowUp'), 0);
    assert.equal(nextRadioIndex(1, 'Home'), 0);
    assert.equal(nextRadioIndex(0, 'End'), 1);
    assert.equal(nextRadioIndex(0, 'Enter'), null);
});

test('verifyEditorPassword usa GET /api/auth/check: 204 aceita, 401 e 503 rejeitam', async () => {
    memoryStorage();
    const original = globalThis.fetch;
    try {
        setEditorPassword('velha');
        globalThis.fetch = async (url, options) => {
            assert.match(String(url), /\/api\/auth\/check$/);
            assert.equal(options.method, 'GET');
            assert.equal(options.headers['X-Editor-Password'], 'certa');
            assert.equal(options.method === 'DELETE', false);
            return {
                ok: true,
                status: 204,
                json: async () => {
                    throw new Error('204 sem corpo');
                }
            };
        };
        assert.equal(await verifyEditorPassword('certa'), true);
        assert.equal(getEditorPassword(), 'velha');

        globalThis.fetch = async (url, options) => {
            assert.match(String(url), /\/api\/auth\/check$/);
            assert.equal(options.method, 'GET');
            assert.equal(options.headers['X-Editor-Password'], 'errada');
            return {
                ok: false,
                status: 401,
                json: async () => ({ detail: 'Senha do editor ausente ou inválida.' })
            };
        };
        setEditorPassword('errada');
        await assert.rejects(
            () => verifyEditorPassword('errada'),
            (err) => err.status === 401 && /incorreta/.test(err.message)
        );
        assert.equal(getEditorPassword(), '');

        globalThis.fetch = async () => ({
            ok: false,
            status: 503,
            json: async () => ({ detail: 'EDITOR_PASSWORD não está definida no ambiente do servidor.' })
        });
        setEditorPassword('qualquer');
        await assert.rejects(
            () => verifyEditorPassword('qualquer'),
            (err) => err.status === 503 && /não está configurada/.test(err.message)
        );
        assert.equal(getEditorPassword(), '');
    } finally {
        globalThis.fetch = original;
        clearEditorPassword();
    }
});

test('nenhum código valida a senha com DELETE', () => {
    const skip = new Set(['node_modules', 'tests']);
    const files = [];
    const walk = (dir) => {
        for (const entry of readdirSync(dir, { withFileTypes: true })) {
            if (skip.has(entry.name) || entry.name === 'dist' || entry.name === 'vendor') continue;
            const full = path.join(dir, entry.name);
            if (entry.isDirectory()) walk(full);
            else if (/\.(js|ts|tsx|html|css)$/.test(entry.name)) files.push(full);
        }
    };
    walk(frontendRoot);
    files.forEach((file) => {
        const text = readFileSync(file, 'utf8');
        assert.equal(text.includes('2147483647'), false, file);
        assert.equal(/DELETE\s+\/api\/routes\/2147483647/.test(text), false, file);
        assert.equal(/\/api\/routes\/2147483647/.test(text), false, file);
    });
    const api = readFileSync(path.join(frontendRoot, 'src/core/api.ts'), 'utf8');
    assert.match(api, /request\('\/api\/auth\/check',\s*\{\s*method:\s*'GET'/);
});

test('páginas de visitante e de admin carregam o seletor', () => {
    const home = readFileSync(path.join(frontendRoot, 'index.html'), 'utf8');
    const entry = readFileSync(path.join(frontendRoot, 'src/main.tsx'), 'utf8');
    assert.match(home, /\/src\/main\.tsx/);
    assert.match(entry, /['"]\.\/boot['"]/);
    ['viewer.html', 'locate.html'].forEach((page) => {
        const html = readFileSync(path.join(frontendRoot, page), 'utf8');
        assert.match(html, /\/src\/boot\.ts/, page);
    });
    ['admin/index.html', 'admin/editor.html', 'admin/recorder.html', 'admin/map-config.html', 'admin/qrcodes.html'].forEach((page) => {
        const html = readFileSync(path.join(frontendRoot, page), 'utf8');
        assert.match(html, /\/src\/boot\.ts/, page);
        assert.match(html, /id="admin-header"/, page);
    });
    const viewer = readFileSync(path.join(frontendRoot, 'viewer.html'), 'utf8');
    const locate = readFileSync(path.join(frontendRoot, 'locate.html'), 'utf8');
    const nav = readFileSync(path.join(frontendRoot, 'src/components/nav.ts'), 'utf8');
    assert.match(viewer, /Mapa do prédio/);
    assert.match(locate, /Navegar/);
    assert.match(nav, /Mapa do prédio/);
    assert.match(nav, /Navegar/);
    assert.doesNotMatch(nav, /editor\.html/);
    assert.doesNotMatch(nav, /recorder\.html/);
    assert.doesNotMatch(home, /href="editor\.html"/);
    assert.doesNotMatch(home, /href="recorder\.html"/);
});
