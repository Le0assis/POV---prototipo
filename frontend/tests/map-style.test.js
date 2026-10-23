import assert from 'node:assert/strict';
import { test } from 'vitest';

import {
    chooseLabels,
    defaultLayerVisibility,
    LABEL_MIN_ZOOM,
    lineWeight,
    readLayerVisibility,
    routeWeight,
    saveLayerVisibility
} from '../src/map/style.ts';

function memoryStorage(initial) {
    const bag = new Map(initial || []);
    return {
        getItem(key) {
            return bag.has(key) ? bag.get(key) : null;
        },
        setItem(key, value) {
            bag.set(key, String(value));
        }
    };
}

test('camadas nascem ligadas e o JSON inválido não apaga o padrão', () => {
    const storage = memoryStorage();
    assert.deepEqual(readLayerVisibility(storage), defaultLayerVisibility());
    const saved = saveLayerVisibility({ plan: false, labels: false }, storage);
    assert.equal(saved.plan, false);
    assert.equal(saved.labels, false);
    assert.equal(saved.route, true);
    assert.deepEqual(readLayerVisibility(storage), saved);
    assert.deepEqual(readLayerVisibility(memoryStorage([['pov.map.layers', '{']])), defaultLayerVisibility());
});

test('a espessura acompanha o zoom e o gravado fica contínuo mais grosso', () => {
    assert.equal(lineWeight(0, true), 4);
    assert.equal(lineWeight(0, false), 3);
    assert.ok(lineWeight(2, true) > lineWeight(0, true));
    assert.ok(lineWeight(-3, false) >= 2);
    assert.equal(routeWeight(0), 8);
    assert.ok(routeWeight(2) > routeWeight(0));
});

test('rótulos: origem e destino sempre, o resto só acima do zoom e sem sobrepor', () => {
    const items = [
        { id: 'origem', name: 'Recepção', pinned: true, x: 0, y: 0 },
        { id: 'destino', name: 'Sala', pinned: true, x: 2, y: 0 },
        { id: 'perto', name: 'Copa', pinned: false, x: 4, y: 0 },
        { id: 'longe', name: 'Biblioteca', pinned: false, x: 200, y: 0 }
    ];
    assert.deepEqual(chooseLabels(items, { zoom: 0 }), ['origem', 'destino']);
    const shown = chooseLabels(items, { zoom: LABEL_MIN_ZOOM });
    assert.deepEqual(shown, ['origem', 'destino', 'longe']);
    assert.deepEqual(chooseLabels(items, { labelsOn: false, zoom: 3 }), []);
});
