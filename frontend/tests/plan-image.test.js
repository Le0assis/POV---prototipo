import assert from 'node:assert/strict';
import { test } from 'vitest';

import { resolvePlanImage } from '../src/map/floor-map.ts';

test('a planta relativa resolve na raiz do frontend, também em /admin/', () => {
    assert.equal(
        resolvePlanImage('assets/planta.png', 'http://127.0.0.1:8000/admin/editor.html'),
        'http://127.0.0.1:8000/assets/planta.png'
    );
    assert.equal(
        resolvePlanImage('assets/planta.png', 'https://user.github.io/pov/admin/map-config.html?x=1#h'),
        'https://user.github.io/pov/assets/planta.png'
    );
    assert.equal(
        resolvePlanImage('assets/planta.png', 'https://pov-unimar.com/viewer.html'),
        'https://pov-unimar.com/assets/planta.png'
    );
    assert.equal(
        resolvePlanImage('https://cdn.example/p.png', 'http://127.0.0.1:8000/admin/editor.html'),
        'https://cdn.example/p.png'
    );
});
