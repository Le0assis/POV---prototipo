import assert from 'node:assert/strict';
import { test, vi } from 'vitest';

import {
    clearEditorPassword,
    getMap,
    READ_TIMEOUT_MS,
    requestTimeout,
    saveCheckpoint,
    setEditorPassword,
    verifyEditorPassword,
    WRITE_TIMEOUT_MS
} from '../src/core/api.ts';

function memoryStorage() {
    const store = new Map();
    globalThis.sessionStorage = {
        getItem: (key) => (store.has(key) ? store.get(key) : null),
        setItem: (key, value) => store.set(key, String(value)),
        removeItem: (key) => store.delete(key)
    };
}

function hang(signal) {
    return new Promise((_resolve, reject) => {
        const fail = () => {
            const err = new Error('aborted');
            err.name = 'AbortError';
            reject(err);
        };
        if (signal.aborted) fail();
        else signal.addEventListener('abort', fail, { once: true });
    });
}

test('escrita e login esperam 15s; leitura continua em 8s', () => {
    assert.equal(READ_TIMEOUT_MS, 8000);
    assert.equal(WRITE_TIMEOUT_MS, 15000);
    assert.equal(requestTimeout('GET', '/api/map'), READ_TIMEOUT_MS);
    assert.equal(requestTimeout('HEAD', '/api/health'), READ_TIMEOUT_MS);
    assert.equal(requestTimeout('POST', '/api/checkpoints'), WRITE_TIMEOUT_MS);
    assert.equal(requestTimeout('PATCH', '/api/checkpoints/Sala/position'), WRITE_TIMEOUT_MS);
    assert.equal(requestTimeout('PUT', '/api/map-config'), WRITE_TIMEOUT_MS);
    assert.equal(requestTimeout('DELETE', '/api/routes/1'), WRITE_TIMEOUT_MS);
    assert.equal(requestTimeout('GET', '/api/auth/check'), WRITE_TIMEOUT_MS);
    assert.equal(requestTimeout('POST', '/api/edges/process-raw', 30000), 30000);
    assert.equal(requestTimeout('GET', '/api/health', 4000), 4000);
});

test('o aborto da leitura chega aos 8s e o da escrita e do login aos 15s', async () => {
    memoryStorage();
    setEditorPassword('guardada');
    const original = globalThis.fetch;
    vi.useFakeTimers();
    try {
        globalThis.fetch = (_url, options) => hang(options.signal);

        const read = track(getMap());
        await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS - 1);
        assert.equal(read.done, false);
        await vi.advanceTimersByTimeAsync(1);
        assert.equal(read.done, true);
        assert.match(read.error.message, /esgotado/);

        const write = track(saveCheckpoint('Sala'));
        await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS);
        assert.equal(write.done, false);
        await vi.advanceTimersByTimeAsync(WRITE_TIMEOUT_MS - READ_TIMEOUT_MS);
        assert.equal(write.done, true);
        assert.match(write.error.message, /esgotado/);

        const login = track(verifyEditorPassword('guardada'));
        await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS);
        assert.equal(login.done, false);
        await vi.advanceTimersByTimeAsync(WRITE_TIMEOUT_MS - READ_TIMEOUT_MS);
        assert.equal(login.done, true);
        assert.match(login.error.message, /esgotado/);
    } finally {
        vi.useRealTimers();
        globalThis.fetch = original;
        clearEditorPassword();
    }
});

function track(promise) {
    const box = { done: false, error: null };
    promise.then(
        () => { box.done = true; },
        (error) => { box.done = true; box.error = error; }
    );
    return box;
}
