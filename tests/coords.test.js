import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
    metersToPixels,
    pixelsToMeters,
    plantHeadingToScreenDeg,
    pixelDistanceMeters
} from '../js/map/coords.js';

const anchor = { pos_x_px: 100, pos_y_px: 200 };
const flat = { px_per_m: 10, rotation_rad: 0 };

test('sem rotação, y da imagem inverte o y local', () => {
    const px = metersToPixels({ x: 2, y: 1 }, anchor, flat);
    assert.deepEqual(px, { x: 120, y: 190 });
});

test('rotação de 90° anti-horária depois do −y', () => {
    const config = { px_per_m: 10, rotation_rad: Math.PI / 2 };
    const px = metersToPixels({ x: 2, y: 3 }, { pos_x_px: 5, pos_y_px: 7 }, config);
    assert.ok(Math.abs(px.x - 35) < 1e-9);
    assert.ok(Math.abs(px.y - 27) < 1e-9);
});

test('a origem local cai na âncora', () => {
    const px = metersToPixels({ x: 0, y: 0 }, anchor, flat);
    assert.deepEqual(px, { x: 100, y: 200 });
});

test('pixelsToMeters desfaz a conversão', () => {
    const config = { px_per_m: 42.5, rotation_rad: 0.4 };
    const origin = { pos_x_px: 412, pos_y_px: 288.5 };
    const local = { x: 3.25, y: -1.5 };
    const px = metersToPixels(local, origin, config);
    const back = pixelsToMeters(px, origin, config);
    assert.ok(Math.abs(back.x - local.x) < 1e-9);
    assert.ok(Math.abs(back.y - local.y) < 1e-9);
});

test('rejeita escala zero e âncora ausente', () => {
    assert.equal(metersToPixels({ x: 1, y: 1 }, anchor, { px_per_m: 0, rotation_rad: 0 }), null);
    assert.equal(metersToPixels({ x: 1, y: 1 }, { pos_x_px: null, pos_y_px: 1 }, flat), null);
});

test('heading 0 sem rotação aponta para a direita na tela', () => {
    const deg = plantHeadingToScreenDeg(0, 0);
    assert.ok(Math.abs(deg - 90) < 1e-9);
});

test('heading +y sem rotação aponta para cima na tela', () => {
    const deg = plantHeadingToScreenDeg(Math.PI / 2, 0);
    assert.ok(Math.abs(deg) < 1e-9);
});

test('distância em metros independe da rotação da planta', () => {
    const a = metersToPixels({ x: 0, y: 0 }, anchor, { px_per_m: 10, rotation_rad: 0.3 });
    const b = metersToPixels({ x: 3, y: 4 }, anchor, { px_per_m: 10, rotation_rad: 0.3 });
    assert.ok(Math.abs(pixelDistanceMeters(a, b, 10) - 5) < 1e-9);
});
