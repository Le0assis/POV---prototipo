import assert from 'node:assert/strict';
import { test } from 'vitest';

import {
    clearEditorPassword,
    getEditorPassword,
    PASSWORD_MISCONFIGURED_MESSAGE,
    PASSWORD_UNCONFIGURED_MESSAGE,
    saveCheckpoint,
    SERVER_BUSY_MESSAGE,
    setEditorPassword,
    verifyEditorPassword
} from '../src/core/api.ts';

const MISSING_HASH = 'EDITOR_PASSWORD_HASH não está definida no ambiente do servidor.';
const BAD_HASH = 'EDITOR_PASSWORD_HASH não é um hash argon2id válido.';
const SLOT_BUSY = 'Muitas conferências ao mesmo tempo. Tente de novo em instantes.';
const DB_BUSY = 'O banco está ocupado. Tente de novo em alguns segundos.';
const DB_DOWN = 'Não foi possível conectar ao MySQL.';

function memoryStorage() {
    const store = new Map();
    globalThis.sessionStorage = {
        getItem: (key) => (store.has(key) ? store.get(key) : null),
        setItem: (key, value) => store.set(key, String(value)),
        removeItem: (key) => store.delete(key)
    };
}

function jsonResponse({ status, detail, retryAfter }) {
    return {
        ok: status >= 200 && status < 300,
        status,
        headers: {
            get(name) {
                if (String(name).toLowerCase() !== 'retry-after' || retryAfter == null) return null;
                return String(retryAfter);
            }
        },
        json: async () => (detail === undefined ? null : { detail })
    };
}

function installPromptDom() {
    const created = [];
    const keyListeners = [];
    const previous = globalThis.document;
    function make() {
        const node = {
            className: '',
            textContent: '',
            id: '',
            type: '',
            value: '',
            listeners: {},
            setAttribute() {},
            append(...kids) { node.children.push(...kids); },
            appendChild(kid) { node.children.push(kid); return kid; },
            addEventListener(type, fn) { node.listeners[type] = fn; },
            remove() {},
            focus() {},
            children: []
        };
        created.push(node);
        return node;
    }
    globalThis.document = {
        activeElement: { focus() {} },
        createElement() { return make(); },
        body: { appendChild(node) { return node; } },
        addEventListener(type, fn) {
            if (type === 'keydown') keyListeners.push(fn);
        },
        removeEventListener() {}
    };
    return {
        created,
        keyListeners,
        restore() {
            globalThis.document = previous;
        }
    };
}

async function until(ready) {
    for (let i = 0; i < 30 && !ready(); i += 1) await Promise.resolve();
}

test('login: só o hash ausente fala de senha; ocupado e 503 desconhecido pedem para tentar de novo', async () => {
    memoryStorage();
    const original = globalThis.fetch;
    try {
        const cases = [
            {
                detail: MISSING_HASH,
                retryAfter: null,
                message: PASSWORD_UNCONFIGURED_MESSAGE,
                kept: true
            },
            {
                detail: SLOT_BUSY,
                retryAfter: 2,
                message: `${SERVER_BUSY_MESSAGE} (2s)`,
                kept: true
            },
            {
                detail: DB_BUSY,
                retryAfter: 5,
                message: `${SERVER_BUSY_MESSAGE} (5s)`,
                kept: true
            },
            {
                detail: DB_DOWN,
                retryAfter: null,
                message: SERVER_BUSY_MESSAGE,
                kept: true
            },
            {
                detail: BAD_HASH,
                retryAfter: null,
                message: PASSWORD_MISCONFIGURED_MESSAGE,
                kept: true
            },
            {
                detail: 'Senha do editor ausente ou inválida.',
                status: 401,
                message: /incorreta/,
                kept: false
            },
            {
                detail: 'Proibido.',
                status: 403,
                message: /incorreta/,
                kept: false
            }
        ];
        for (const item of cases) {
            setEditorPassword('guardada');
            globalThis.fetch = async () => jsonResponse({
                status: item.status || 503,
                detail: item.detail,
                retryAfter: item.retryAfter
            });
            await assert.rejects(
                () => verifyEditorPassword('guardada'),
                (err) => err.status === (item.status || 503) && (
                    item.message instanceof RegExp ? item.message.test(err.message) : err.message === item.message
                )
            );
            assert.equal(getEditorPassword(), item.kept ? 'guardada' : '', item.detail);
        }
    } finally {
        globalThis.fetch = original;
        clearEditorPassword();
    }
});

test('gravação: 503 de capacidade não apaga a senha e honra o Retry-After', async () => {
    memoryStorage();
    const original = globalThis.fetch;
    try {
        const cases = [
            { detail: MISSING_HASH, retryAfter: null, message: PASSWORD_UNCONFIGURED_MESSAGE },
            { detail: SLOT_BUSY, retryAfter: 2, message: `${SERVER_BUSY_MESSAGE} (2s)` },
            { detail: 'falha inesperada', retryAfter: null, message: SERVER_BUSY_MESSAGE }
        ];
        for (const item of cases) {
            setEditorPassword('guardada');
            globalThis.fetch = async () => jsonResponse({
                status: 503,
                detail: item.detail,
                retryAfter: item.retryAfter
            });
            await assert.rejects(
                () => saveCheckpoint('Sala'),
                (err) => err.status === 503 && err.message === item.message
            );
            assert.equal(getEditorPassword(), 'guardada', item.detail);
        }
    } finally {
        globalThis.fetch = original;
        clearEditorPassword();
    }
});

test('gravação: 401 e 403 apagam a senha; o 503 da nova tentativa não apaga', async () => {
    memoryStorage();
    const originalFetch = globalThis.fetch;
    const dom = installPromptDom();
    try {
        setEditorPassword('velha');
        globalThis.fetch = async () => jsonResponse({
            status: 401,
            detail: 'Senha do editor ausente ou inválida.'
        });
        const rejected = saveCheckpoint('Sala');
        await until(() => dom.keyListeners.length > 0);
        assert.equal(getEditorPassword(), '');
        dom.keyListeners[0]({ key: 'Escape', preventDefault() {} });
        await assert.rejects(rejected, (err) => err.status === 401);

        setEditorPassword('velha');
        dom.keyListeners.length = 0;
        globalThis.fetch = async () => jsonResponse({ status: 403, detail: 'Proibido.' });
        const forbidden = saveCheckpoint('Copa');
        await until(() => dom.keyListeners.length > 0);
        assert.equal(getEditorPassword(), '');
        dom.keyListeners[0]({ key: 'Escape', preventDefault() {} });
        await assert.rejects(forbidden, (err) => err.status === 401 && /incorreta/.test(err.message));

        setEditorPassword('velha');
        let calls = 0;
        globalThis.fetch = async (_url, options) => {
            calls += 1;
            if (calls === 1) {
                return jsonResponse({ status: 401, detail: 'Senha do editor ausente ou inválida.' });
            }
            assert.equal(options.headers['X-Editor-Password'], 'nova');
            return jsonResponse({
                status: 503,
                detail: DB_BUSY,
                retryAfter: 5
            });
        };
        const before = dom.created.length;
        const retry = saveCheckpoint('Hall');
        await until(() => dom.created.slice(before).some((node) => node.listeners.submit));
        const fresh = dom.created.slice(before);
        const form = fresh.find((node) => node.listeners.submit);
        const input = fresh.find((node) => node.type === 'password');
        input.value = 'nova';
        form.listeners.submit({ preventDefault() {} });
        await assert.rejects(
            retry,
            (err) => err.status === 503 && err.message === `${SERVER_BUSY_MESSAGE} (5s)` && err.retryAfter === 5
        );
        assert.equal(getEditorPassword(), 'nova');
        assert.equal(calls, 2);
    } finally {
        globalThis.fetch = originalFetch;
        dom.restore();
        clearEditorPassword();
    }
});
