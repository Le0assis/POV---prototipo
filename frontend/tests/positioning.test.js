import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'vitest';

import { relativeHeadingRad } from '../src/sensors/angles.ts';
import { snapToPolylines } from '../src/route/snap.ts';
import { computeRoute, planRoute } from '../src/nav/routing.ts';
import {
    ARRIVAL_M,
    NO_SENSORS_NOTICE,
    buildRouteFrame,
    createPositionTracker,
    nextManeuver,
    recalibrateRoute,
    resolveSensorMode,
    snapToRoute,
    turnDirection
} from '../src/nav/positioning.ts';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const flat = { px_per_m: 10, rotation_rad: 0 };

function cp(slug, name, x, y) {
    return { slug, name, pos_x_px: x, pos_y_px: y };
}

function close(actual, expected, epsilon = 1e-6) {
    assert.ok(Math.abs(actual - expected) < epsilon, `${actual} ≠ ${expected}`);
}

test('a conversão de heading não é duplicada fora de angles.ts', () => {
    const text = readFileSync(path.join(root, 'src/nav/positioning.ts'), 'utf8');
    assert.equal(text.includes('relativeHeadingRad'), true);
    assert.equal(text.includes('HEADING_CONVENTION'), false);
    assert.equal(text.includes('/api/reset'), false);
});

test('rota reta: os passos andam na polilinha e o heading relativo gira o cone', () => {
    const tracker = createPositionTracker([{ x: 0, y: 0 }, { x: 30, y: 0 }]);
    tracker.anchor({ x: 0, y: 0, bearingDeg: 10, referenceRad: 0 });
    let pose = tracker.applyStep(2, 10);
    close(pose.point.x, 2);
    close(pose.point.y, 0);
    close(pose.headingRad, 0);
    pose = tracker.applyStep(3, 10);
    close(pose.point.x, 5);
    close(pose.point.y, 0);
    pose = tracker.poseAt(10 + 90);
    close(pose.headingRad, relativeHeadingRad(100, 10, 0));
    assert.ok(pose.headingRad < 0);
});

test('curva: o passo com o novo heading entra no trecho seguinte', () => {
    const tracker = createPositionTracker([
        { x: 0, y: 0 },
        { x: 10, y: 0 },
        { x: 10, y: 10 }
    ]);
    tracker.anchor({ x: 0, y: 0, bearingDeg: 0, referenceRad: 0 });
    const corner = tracker.applyStep(10, 0);
    close(corner.point.x, 10, 1e-6);
    close(corner.point.y, 0, 1e-6);
    const turned = tracker.applyStep(4, 270);
    close(turned.point.x, 10, 0.05);
    close(turned.point.y, 4, 0.05);
    close(turned.headingRad, Math.PI / 2, 1e-6);
});

test('o encaixe fica na rota mesmo quando outra aresta do grafo está mais perto', () => {
    const route = [{ x: 0, y: 0 }, { x: 20, y: 0 }];
    const other = [{ x: 0, y: 1.5 }, { x: 20, y: 1.5 }];
    const free = { x: 2 * Math.cos(80 * Math.PI / 180), y: 2 * Math.sin(80 * Math.PI / 180) };
    const onRoute = snapToRoute(free, route);
    const onGraph = snapToPolylines(free, [
        { id: 'route', points: route },
        { id: 'other', points: other }
    ]);
    close(onRoute.point.y, 0);
    assert.equal(onGraph.id, 'other');
    assert.ok(onGraph.point.y > 1);

    const tracker = createPositionTracker(route);
    tracker.anchor({ x: 0, y: 0, bearingDeg: 0, referenceRad: 0 });
    const pose = tracker.applyStep(2, -80);
    close(pose.point.y, 0, 1e-6);
    assert.ok(pose.point.x > 0);
    assert.ok(pose.point.x < 2);
});

test('instruções: em frente, esquerda, direita e chegada', () => {
    const straight = {
        segments: [
            { name: 'Meio', slug: 'meio', lengthM: 10, headingRad: 0, endHeading: 0 },
            { name: 'Sala', slug: 'sala', lengthM: 10, headingRad: 0, endHeading: 0 }
        ]
    };
    const ahead = nextManeuver(straight, 0);
    assert.equal(ahead.kind, 'straight');
    assert.equal(ahead.text, 'Siga em frente por 20 m');
    assert.equal(turnDirection(0, 30 * Math.PI / 180), 'straight');
    assert.equal(turnDirection(0, -30 * Math.PI / 180), 'straight');

    const left = nextManeuver({
        segments: [
            { name: 'Corredor B', slug: 'corredor', lengthM: 12, headingRad: 0, endHeading: 0 },
            { name: 'Sala', slug: 'sala', lengthM: 8, headingRad: Math.PI / 2, endHeading: Math.PI / 2 }
        ]
    }, 0);
    assert.equal(left.kind, 'left');
    assert.equal(left.text, 'Siga 12 m e vire à esquerda em Corredor B');

    const right = nextManeuver({
        segments: [
            { name: 'Corredor B', slug: 'corredor', lengthM: 12, headingRad: 0, endHeading: 0 },
            { name: 'Sala', slug: 'sala', lengthM: 8, headingRad: -Math.PI / 2, endHeading: -Math.PI / 2 }
        ]
    }, 0);
    assert.equal(right.kind, 'right');
    assert.equal(right.text, 'Siga 12 m e vire à direita em Corredor B');
    assert.equal(turnDirection(0, 31 * Math.PI / 180), 'left');
    assert.equal(turnDirection(0, -31 * Math.PI / 180), 'right');

    const done = nextManeuver(straight, 20 - ARRIVAL_M);
    assert.equal(done.kind, 'arrival');
    assert.equal(done.text, 'Você chegou a Sala');
    const before = nextManeuver(straight, 20 - ARRIVAL_M - 0.2);
    assert.equal(before.kind, 'straight');
});

test('a rota desenhada gera a curva à direita e a chegada a 2 m', () => {
    const route = computeRoute({
        origin: 'recepcao',
        destination: 'sala',
        checkpoints: [
            cp('recepcao', 'Recepção', 80, 300),
            cp('corredor', 'Corredor B', 280, 300),
            cp('sala', 'Sala', 280, 480)
        ],
        connections: [
            { edge_id: 1, source: 'Recepção', target: 'Corredor B', origin: 'manual', edge_distance_m: 20 },
            { edge_id: 2, source: 'Corredor B', target: 'Sala', origin: 'manual', edge_distance_m: 18 }
        ],
        mapConfig: flat
    });
    const frame = buildRouteFrame(route, flat);
    const banner = nextManeuver(frame, 8);
    assert.equal(banner.kind, 'right');
    assert.equal(banner.text, 'Siga 12 m e vire à direita em Corredor B');
    const arrived = nextManeuver(frame, frame.lengthM - 2);
    assert.equal(arrived.kind, 'arrival');
    assert.equal(arrived.text, 'Você chegou a Sala');
});

test('recalibrar na rota não refaz o caminho; fora dela, recalcula', () => {
    const checkpoints = [
        cp('recepcao', 'Recepção', 0, 0),
        cp('corredor', 'Corredor B', 200, 0),
        cp('sala', 'Sala', 200, 180),
        cp('copa', 'Copa', 0, 180)
    ];
    const connections = [
        { edge_id: 1, source: 'Recepção', target: 'Corredor B', origin: 'manual', edge_distance_m: 20 },
        { edge_id: 2, source: 'Corredor B', target: 'Sala', origin: 'manual', edge_distance_m: 18 },
        { edge_id: 3, source: 'Copa', target: 'Sala', origin: 'manual', edge_distance_m: 20 }
    ];
    const route = computeRoute({
        origin: 'recepcao',
        destination: 'sala',
        checkpoints,
        connections,
        mapConfig: flat
    });
    let calls = 0;
    const kept = recalibrateRoute({
        route,
        checkpointSlug: 'corredor',
        destinationSlug: 'sala',
        plan: () => {
            calls += 1;
            return { ok: true, route: null };
        }
    });
    assert.equal(calls, 0);
    assert.equal(kept.recalculated, false);
    assert.equal(kept.route, route);
    assert.equal(kept.announcement, '');

    const tracker = createPositionTracker(buildRouteFrame(route, flat).points);
    tracker.anchor({ x: 0, y: 0, bearingDeg: 0, referenceRad: 0 });
    tracker.applyStep(5, 0);
    const reset = tracker.anchor({ x: 20, y: 0, bearingDeg: 15, referenceRad: -Math.PI / 2 });
    close(reset.point.x, 20, 1e-6);
    close(reset.point.y, 0, 1e-6);
    close(reset.headingRad, -Math.PI / 2, 1e-6);

    const moved = recalibrateRoute({
        route,
        checkpointSlug: 'copa',
        destinationSlug: 'sala',
        plan: ({ origin, destination }) => planRoute({
            origin,
            destination,
            checkpoints,
            connections,
            mapConfig: flat
        })
    });
    assert.equal(moved.ok, true);
    assert.equal(moved.recalculated, true);
    assert.equal(moved.announcement, 'Rota recalculada');
    assert.deepEqual(moved.route.checkpoints.map((item) => item.slug), ['copa', 'sala']);

    const failed = recalibrateRoute({
        route,
        checkpointSlug: 'inexistente',
        destinationSlug: 'sala',
        plan: () => planRoute({
            origin: 'inexistente',
            destination: 'sala',
            checkpoints,
            connections,
            mapConfig: flat
        })
    });
    assert.equal(failed.ok, false);
    assert.equal(failed.recalculated, false);
    assert.equal(failed.route, route);
});

test('sem sensores: permissão negada ou API ausente cai no aviso, sem chamar o servidor', () => {
    assert.equal(NO_SENSORS_NOTICE, 'Sem sensores: siga a rota no mapa e leia os QR codes pelo caminho');
    assert.equal(resolveSensorMode({ present: false, motionGranted: true, orientationGranted: true }), 'fallback');
    assert.equal(resolveSensorMode({
        present: true,
        motionGranted: false,
        orientationGranted: true
    }), 'fallback');
    assert.equal(resolveSensorMode({
        present: true,
        motionGranted: true,
        orientationGranted: false
    }), 'fallback');
    assert.equal(resolveSensorMode({
        present: true,
        motionGranted: true,
        orientationGranted: true,
        forcedOff: true
    }), 'fallback');
    assert.equal(resolveSensorMode({
        present: true,
        motionGranted: true,
        orientationGranted: true
    }), 'live');

    const tracker = createPositionTracker([{ x: 0, y: 0 }, { x: 12, y: 0 }]);
    const parked = tracker.anchor({ x: 0, y: 0, bearingDeg: null, referenceRad: 0 });
    close(parked.point.x, 0);
    const moved = tracker.anchor({ x: 12, y: 0, bearingDeg: null, referenceRad: 0 });
    close(moved.point.x, 12);
    close(moved.remainingM, 0);
    assert.equal(nextManeuver({
        segments: [{ name: 'Sala', slug: 'sala', lengthM: 12, headingRad: 0, endHeading: 0 }]
    }, moved.alongM).kind, 'arrival');
});
