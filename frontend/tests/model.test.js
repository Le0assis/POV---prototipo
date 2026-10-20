import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
    checkpointAnchor,
    isRecordedConnection,
    connectionPath,
    pathFromProcessResponse,
    edgeIdOf
} from '../js/route/model.js';
import { normalizePdrConfig } from '../js/route/pdr-config.js';

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

test('path vigente prefere o campo path e senão o trace ativo', () => {
    const direct = connectionPath({ path: [{ x: 0, y: 0 }], traces: [] });
    assert.equal(direct.length, 1);
    const fromTrace = connectionPath({
        active_trace_id: 7,
        traces: [
            { trace_id: 3, path: [{ x: 1, y: 1 }] },
            { trace_id: 7, path: [{ x: 2, y: 2 }, { x: 3, y: 3 }] }
        ]
    });
    assert.equal(fromTrace.length, 3);
    assert.equal(fromTrace[0].x, 0);
    assert.equal(isRecordedConnection({
        origin: 'recording',
        active_trace_id: 7,
        path: [{ x: 0, y: 0 }, { x: 1, y: 0 }]
    }), true);
    assert.equal(isRecordedConnection({
        origin: 'manual',
        active_trace_id: null,
        path: [{ x: 0, y: 0 }, { x: 1, y: 0 }]
    }), false);
});

test('path do PR #2 é objeto com points e ganha a origem', () => {
    const points = connectionPath({
        id: 42,
        origin: 'recording',
        active_trace_id: 7,
        path: {
            id: 7,
            points: [{ x: 0.66, y: 0.01, t: 10 }, { x: 1.3, y: 0.02, t: 11 }]
        }
    });
    assert.equal(points.length, 3);
    assert.deepEqual(points[0], { x: 0, y: 0, t: null });
    assert.equal(edgeIdOf({ id: 42 }), 42);
    assert.equal(isRecordedConnection({
        origin: 'recording',
        active_trace_id: 7,
        path: { id: 7, points: [{ x: 0.66, y: 0.01 }] }
    }), true);
});

test('process-raw devolve path.points', () => {
    const path = pathFromProcessResponse({
        path: { id: 17, points: [{ x: 1, y: 0, t: 2 }] }
    });
    assert.equal(path[0].x, 0);
    assert.equal(path[1].x, 1);
});

test('process-raw com path array e origem não duplica o (0, 0)', () => {
    const path = pathFromProcessResponse({
        path: [{ x: 0, y: 0, t: 1 }, { x: 2, y: 0, t: 2 }]
    });
    assert.equal(path.length, 2);
    assert.equal(path[0].x, 0);
    assert.equal(path[1].x, 2);
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

test('pdr config plano do PR #2 vira step_length', () => {
    const cfg = normalizePdrConfig({
        weinberg_k: 0.45,
        step_min_m: 0.4,
        step_max_m: 0.6,
        min_step_interval_s: 0.33,
        lowpass_cutoff_hz: 2.2
    });
    assert.equal(cfg.step_length.k, 0.45);
    assert.equal(cfg.step_length.min_m, 0.4);
    assert.equal(cfg.step_length.default_m, 0.5);
    assert.equal(cfg.step_detection.lowpass_cutoff_hz, 2.2);
});

test('pdr config agrupado da spec permanece intacto', () => {
    const raw = {
        step_length: { k: 0.4, min_m: 0.3, max_m: 0.9, default_m: 0.7 },
        step_detection: { lowpass_cutoff_hz: 2 },
        localization: { snap_end_window_m: 1.5 }
    };
    const cfg = normalizePdrConfig(raw);
    assert.equal(cfg, raw);
    assert.equal(cfg.step_length.default_m, 0.7);
    assert.equal(cfg.localization.snap_end_window_m, 1.5);
});
