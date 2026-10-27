import assert from 'node:assert/strict';
import { test } from 'vitest';

import {
    metersToPixels as coordsMeters,
    pixelsToMeters as coordsInverse
} from '../src/map/coords.ts';
import {
    formatUserMeters,
    metersToPixels,
    pixelDistanceMeters,
    pixelsToMeters,
    plantHeadingToScreenDeg,
    stripPixelWording
} from '../src/map/units.ts';

const anchor = { pos_x_px: 100, pos_y_px: 200 };
const flat = { px_per_m: 10, rotation_rad: 0 };

test('units.js é a mesma conversão que o viewer e o locate usam', () => {
    assert.equal(metersToPixels, coordsMeters);
    assert.equal(pixelsToMeters, coordsInverse);
});

test('sem rotação, y da imagem inverte o y local', () => {
    assert.deepEqual(metersToPixels({ x: 2, y: 1 }, anchor, flat), { x: 120, y: 190 });
});

test('rotação de 90° anti-horária depois do −y', () => {
    const px = metersToPixels(
        { x: 2, y: 3 },
        { pos_x_px: 5, pos_y_px: 7 },
        { px_per_m: 10, rotation_rad: Math.PI / 2 }
    );
    assert.ok(Math.abs(px.x - 35) < 1e-9);
    assert.ok(Math.abs(px.y - 27) < 1e-9);
});

test('a origem local cai na âncora e o inverso desfaz', () => {
    assert.deepEqual(metersToPixels({ x: 0, y: 0 }, anchor, flat), { x: 100, y: 200 });
    const config = { px_per_m: 42.5, rotation_rad: 0.4 };
    const origin = { pos_x_px: 412, pos_y_px: 288.5 };
    const local = { x: 3.25, y: -1.5 };
    const back = pixelsToMeters(metersToPixels(local, origin, config), origin, config);
    assert.ok(Math.abs(back.x - local.x) < 1e-9);
    assert.ok(Math.abs(back.y - local.y) < 1e-9);
});

test('rejeita escala zero e âncora ausente', () => {
    assert.equal(metersToPixels({ x: 1, y: 1 }, anchor, { px_per_m: 0, rotation_rad: 0 }), null);
    assert.equal(metersToPixels({ x: 1, y: 1 }, { pos_x_px: null, pos_y_px: 1 }, flat), null);
});

test('o visitante vê metros e não vê pixel', () => {
    assert.equal(formatUserMeters(12.4, 0), '12 m');
    assert.equal(formatUserMeters(1.256, 2), '1.26 m');
    assert.equal(stripPixelWording('parede de 400 px, px_per_m = 100'), 'parede de');
    assert.equal(stripPixelWording('~12 m'), '~12 m');
});

test('heading do plano e distância em metros', () => {
    assert.ok(Math.abs(plantHeadingToScreenDeg(0, 0) - 90) < 1e-9);
    assert.ok(Math.abs(plantHeadingToScreenDeg(Math.PI / 2, 0)) < 1e-9);
    const a = metersToPixels({ x: 0, y: 0 }, anchor, { px_per_m: 10, rotation_rad: 0.3 });
    const b = metersToPixels({ x: 3, y: 4 }, anchor, { px_per_m: 10, rotation_rad: 0.3 });
    assert.ok(Math.abs(pixelDistanceMeters(a, b, 10) - 5) < 1e-9);
});
