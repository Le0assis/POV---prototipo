import assert from 'node:assert/strict';
import { test } from 'vitest';

import { compassNeedleDeg, relativeHeadingRad } from '../src/sensors/angles.ts';

test('a agulha aponta para cima com norte e planta sem rotação', () => {
    assert.ok(Math.abs(compassNeedleDeg(0, 0)) < 1e-9);
    assert.ok(Math.abs(compassNeedleDeg(90, 0) - 90) < 1e-9);
});

test('a agulha acompanha a rotação da planta', () => {
    const turned = compassNeedleDeg(0, Math.PI / 2);
    assert.ok(Math.abs(turned - 90) < 1e-6);
});

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
