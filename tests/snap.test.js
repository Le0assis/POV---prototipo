import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
    projectByAccumulatedDistance,
    snapToPolylines,
    tangentAtDistance
} from '../js/route/snap.js';
import { nearestCheckpoint, projectWalk, readLocalization } from '../js/route/localize.js';

const path = [
    { x: 0, y: 0 },
    { x: 10, y: 0 },
    { x: 10, y: 10 }
];

test('projeção por distância acumulada segue a polilinha', () => {
    const at = projectByAccumulatedDistance(path, 5, 20);
    assert.ok(Math.abs(at.point.x - 5) < 1e-9);
    assert.ok(Math.abs(at.point.y - 0) < 1e-9);
    assert.ok(Math.abs(at.fraction - 0.25) < 1e-9);
    assert.equal(at.remainingM, 15);
});

test('no fim da aresta o ponto é o último vértice', () => {
    const at = projectWalk(path, 20, 20);
    assert.ok(Math.abs(at.point.x - 10) < 1e-9);
    assert.ok(Math.abs(at.point.y - 10) < 1e-9);
    assert.equal(at.overshootM, 0);
});

test('distância além da aresta fica no fim e registra o excesso', () => {
    const at = projectByAccumulatedDistance(path, 23, 20);
    assert.ok(Math.abs(at.point.x - 10) < 1e-9);
    assert.ok(Math.abs(at.point.y - 10) < 1e-9);
    assert.equal(at.overshootM, 3);
});

test('encaixe no segmento mais próximo', () => {
    const hit = snapToPolylines({ x: 5, y: 2 }, [
        { id: 'longe', points: [{ x: 0, y: 20 }, { x: 10, y: 20 }] },
        { id: 'perto', points: [{ x: 0, y: 0 }, { x: 10, y: 0 }] }
    ]);
    assert.equal(hit.id, 'perto');
    assert.ok(Math.abs(hit.point.x - 5) < 1e-9);
    assert.ok(Math.abs(hit.point.y - 0) < 1e-9);
    assert.ok(Math.abs(hit.distance - 2) < 1e-9);
});

test('encaixe no extremo do segmento', () => {
    const hit = snapToPolylines({ x: -4, y: 1 }, [
        { id: 'a', points: [{ x: 0, y: 0 }, { x: 10, y: 0 }] }
    ]);
    assert.deepEqual(hit.point, { x: 0, y: 0 });
});

test('tangente no primeiro trecho é o eixo +x', () => {
    const h = tangentAtDistance(path, 0, 20);
    assert.ok(Math.abs(h) < 1e-9);
});

test('checkpoint estimado é o mais próximo, com erro em metros', () => {
    const nearest = nearestCheckpoint({ x: 12, y: 5 }, [
        { name: 'A', anchor: { pos_x_px: 0, pos_y_px: 0 } },
        { name: 'B', anchor: { pos_x_px: 10, pos_y_px: 0 } }
    ], 10);
    assert.equal(nearest.name, 'B');
    assert.ok(Math.abs(nearest.errorM - Math.hypot(0.2, 0.5)) < 1e-9);
});

test('localização só aceita a janela vinda do servidor', () => {
    assert.equal(readLocalization(null), null);
    assert.equal(readLocalization({ localization: { snap_end_window_m: 1.5 } }), null);
    const loc = readLocalization({
        localization: {
            method: 'projecao_por_distancia_acumulada',
            snap_end_window_m: 1.5,
            edge_match_tolerance_rad: 0.524
        }
    });
    assert.equal(loc.snapEndWindowM, 1.5);
    assert.equal(loc.edgeMatchToleranceRad, 0.524);
});
