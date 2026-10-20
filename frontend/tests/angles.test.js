import assert from 'node:assert/strict';
import { test } from 'node:test';

import { relativeHeadingRad } from '../js/sensors/angles.js';

test('sem giro, o heading relativo é o heading_rad da aresta', () => {
    const ref = 0.4;
    const h = relativeHeadingRad(30, 30, ref);
    assert.ok(Math.abs(h - ref) < 1e-9);
});

test('giro horário de 90° na bússola reduz o heading do plano', () => {
    const h = relativeHeadingRad(90, 0, 0);
    assert.ok(Math.abs(h - (-Math.PI / 2)) < 1e-9);
});

test('giro anti-horário de 90° na bússola aumenta o heading do plano', () => {
    const h = relativeHeadingRad(270, 0, 0);
    assert.ok(Math.abs(h - (Math.PI / 2)) < 1e-9);
});
