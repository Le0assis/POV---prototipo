import assert from 'node:assert/strict';
import { test } from 'vitest';

import {
    checkpointAnchor,
    isRecordedConnection,
    connectionPath,
    pathFromProcessResponse,
    edgeIdOf,
    normalizeMapConfig
} from '../src/route/model.ts';

test('posição nula não vira pixel 0', () => {
    assert.equal(checkpointAnchor({ pos_x_px: null, pos_y_px: null }), null);
    assert.equal(checkpointAnchor({ pos_x_px: undefined, pos_y_px: 10 }), null);
});

test('pixel 0 é posição válida', () => {
    assert.deepEqual(checkpointAnchor({ pos_x_px: 0, pos_y_px: 0 }), {
        pos_x_px: 0,
        pos_y_px: 0
    });
});

test('path da conexão é o array, com a origem no primeiro ponto', () => {
    const path = connectionPath({
        edge_id: 42,
        origin: 'recorded',
        active_trace_id: 7,
        path: [{ x: 0, y: 0, t: 10 }, { x: 1.3, y: 0.02, t: 11 }]
    });
    assert.equal(path.length, 2);
    assert.equal(path[0].x, 0);
    assert.equal(path[0].y, 0);
    assert.equal(edgeIdOf({ edge_id: 42 }), 42);
    assert.equal(edgeIdOf({ id: 42 }), null);
    assert.equal(isRecordedConnection({
        origin: 'recorded',
        active_trace_id: 7,
        path: [{ x: 0, y: 0, t: 1 }, { x: 1, y: 0, t: 2 }]
    }), true);
    assert.equal(isRecordedConnection({
        origin: 'manual',
        active_trace_id: null,
        path: [{ x: 0, y: 0, t: 1 }, { x: 1, y: 0, t: 2 }]
    }), false);
});

test('objeto path.points não é trajetória', () => {
    const path = connectionPath({
        origin: 'recorded',
        active_trace_id: 7,
        distance_m: 4,
        heading_rad: 0,
        path: { id: 7, points: [{ x: 1, y: 0 }] }
    });
    assert.equal(path.length, 2);
    assert.equal(path[0].x, 0);
    assert.equal(path[1].x, 4);
    assert.equal(isRecordedConnection({
        origin: 'recorded',
        active_trace_id: 7,
        path: { points: [{ x: 0, y: 0 }, { x: 1, y: 0 }] }
    }), false);
});

test('process-raw traz path array e trace_id no topo', () => {
    const body = {
        trace_id: 17,
        path: [{ x: 0, y: 0, t: 1 }, { x: 2, y: 0, t: 2 }]
    };
    const path = pathFromProcessResponse(body);
    assert.equal(path.length, 2);
    assert.equal(path[0].x, 0);
    assert.equal(path[1].x, 2);
    assert.equal(body.trace_id, 17);
    assert.equal(pathFromProcessResponse({
        trace_id: 9,
        path: { points: [{ x: 1, y: 0 }] }
    }).length, 0);
});

test('aresta manual sem path vira reta pelo heading', () => {
    const path = connectionPath({
        origin: 'manual',
        distance_m: 4,
        heading_rad: 0,
        path: null
    });
    assert.equal(path.length, 2);
    assert.ok(Math.abs(path[1].x - 4) < 1e-9);
    assert.ok(Math.abs(path[1].y) < 1e-9);
});

test('map-config só lê o envelope da main', () => {
    const config = normalizeMapConfig({
        status: 'success',
        map_config: { plan_image: 'assets/planta.png', px_per_m: 12, rotation_rad: 0.2 }
    });
    assert.equal(config.px_per_m, 12);
    assert.equal(config.plan_image, 'assets/planta.png');
    assert.equal(config.ready, true);
    assert.equal(normalizeMapConfig({ px_per_m: 12, rotation_rad: 0 }), null);
});
