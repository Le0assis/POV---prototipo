import assert from 'node:assert/strict';
import test from 'node:test';

import {
    SESSION_KEY,
    formatHash,
    hashHasRoute,
    hydrateSession,
    loadSession,
    parseHash,
    pointsFromHash,
    saveSession,
    toStored
} from '../js/core/store.js';

function memoryStorage() {
    const store = new Map();
    return {
        getItem: (key) => (store.has(key) ? store.get(key) : null),
        setItem: (key, value) => store.set(key, String(value))
    };
}

test('hash faz a ida e a volta com espaço, e comercial e unicode', () => {
    const original = {
        origin: { slug: 'sala 1', label: 'Sala 1' },
        destination: { slug: 'café & hall', label: 'Café' },
        state: 'E3'
    };
    const hash = formatHash(original);
    assert.equal(hash.includes(' '), false);
    assert.equal(hash.includes('&hall'), false);
    assert.equal(hash.includes('state'), false);
    assert.equal(hash.includes('E3'), false);

    const parsed = parseHash(hash);
    assert.equal(parsed.origin, 'sala 1');
    assert.equal(parsed.destination, 'café & hall');
    assert.equal(formatHash({ origin: parsed.origin, destination: parsed.destination }), hash);
});

test('decodifica %20 e + como espaço e omite vazio', () => {
    assert.deepEqual(parseHash('#origem=sala%201&destino=a%2Bb'), {
        origin: 'sala 1',
        destination: 'a+b'
    });
    assert.deepEqual(parseHash('#origem=sala+1'), {
        origin: 'sala 1',
        destination: null
    });
    assert.deepEqual(parseHash(''), { origin: null, destination: null });
    assert.deepEqual(parseHash('#origem='), { origin: null, destination: null });
    assert.equal(formatHash({ origin: null, destination: '' }), '');
    assert.equal(hashHasRoute('#destino=sala'), true);
    assert.equal(hashHasRoute(''), false);
    assert.equal(hashHasRoute('#passo=1'), false);
});

test('sessionStorage guarda origem, destino e estado e ignora o resto', () => {
    const storage = memoryStorage();
    const session = {
        origin: { slug: 'recepcao', label: 'Recepção' },
        destination: { slug: 'sala', label: 'Sala' },
        state: 'E2',
        returnTo: 'E3',
        error: 'não persiste'
    };
    saveSession(session, storage);
    const raw = JSON.parse(storage.getItem(SESSION_KEY));
    assert.deepEqual(Object.keys(raw).sort(), ['destination', 'origin', 'state']);
    assert.deepEqual(loadSession(storage), toStored(session));
    assert.equal(loadSession(storage).returnTo, undefined);

    storage.setItem(SESSION_KEY, '{');
    assert.equal(loadSession(storage).state, 'E0');
    storage.setItem(SESSION_KEY, JSON.stringify({ state: 'não-existe', origin: 'portaria' }));
    assert.deepEqual(loadSession(storage), {
        origin: { slug: 'portaria', label: 'portaria' },
        destination: null,
        state: 'E0'
    });
});

test('o hash manda na origem e no destino e preserva o rótulo já conhecido', () => {
    const storage = memoryStorage();
    saveSession({
        origin: { slug: 'recepcao', label: 'Recepção' },
        destination: { slug: 'sala', label: 'Sala' },
        state: 'E4'
    }, storage);

    const fromLink = hydrateSession('#origem=recepcao&destino=biblioteca', storage);
    assert.equal(fromLink.origin.label, 'Recepção');
    assert.equal(fromLink.destination.slug, 'biblioteca');
    assert.equal(fromLink.destination.label, 'biblioteca');
    assert.equal(fromLink.state, 'E4');

    const kept = hydrateSession('', storage);
    assert.equal(kept.destination.label, 'Sala');

    const partial = pointsFromHash(kept, '#origem=hall');
    assert.equal(partial.origin.slug, 'hall');
    assert.equal(partial.destination, null);
    assert.equal(partial.returnTo, null);

    const remembered = pointsFromHash({ ...kept, returnTo: 'E3' }, '');
    assert.equal(remembered.returnTo, 'E3');
    assert.equal(remembered.destination.slug, 'sala');
});
