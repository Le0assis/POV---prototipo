import assert from 'node:assert/strict';
import test from 'node:test';

import { RouteError } from '../js/nav/graph.js';
import {
    computeRoute,
    estimateMinutes,
    formatDistanceLabel,
    formatDurationLabel,
    reverseLocalPath,
    routeAnnouncement,
    selectTracePath,
    stepText
} from '../js/nav/routing.js';
import { chromePadding, fitPadding } from '../js/map/route-layer.js';

const flat = { px_per_m: 10, rotation_rad: 0 };

function cp(slug, name, x, y) {
    return { slug, name, pos_x_px: x, pos_y_px: y };
}

function closeTo(actual, expected) {
    assert.equal(actual.length, expected.length);
    actual.forEach((point, index) => {
        assert.ok(Math.abs(point.x - expected[index].x) < 1e-6, `x ${index}: ${point.x}`);
        assert.ok(Math.abs(point.y - expected[index].y) < 1e-6, `y ${index}: ${point.y}`);
    });
}

test('caminho simples entre dois checkpoints', () => {
    const route = computeRoute({
        origin: 'recepcao',
        destination: 'hall',
        checkpoints: [cp('recepcao', 'Recepção', 100, 200), cp('hall', 'Hall', 300, 200)],
        connections: [{
            edge_id: 1,
            reverse_edge_id: 2,
            source: 'Recepção',
            target: 'Hall',
            origin: 'recorded',
            active_trace_id: 9,
            edge_distance_m: 15,
            traces: [{
                trace_id: 9,
                path: [{ x: 0, y: 0, t: 1 }, { x: 0, y: 1, t: 2 }, { x: 20, y: 0, t: 3 }]
            }]
        }],
        mapConfig: flat
    });
    assert.deepEqual(route.checkpoints.map((item) => item.slug), ['recepcao', 'hall']);
    assert.equal(route.edges.length, 1);
    assert.equal(route.edges[0].direction, 'forward');
    assert.equal(route.distance_m, 15);
    closeTo(route.points, [
        { x: 100, y: 200 },
        { x: 100, y: 190 },
        { x: 300, y: 200 }
    ]);
    assert.equal(route.steps[0].text, 'Siga até Hall (~15 m)');
});

test('escolhe o caminho mais curto', () => {
    const checkpoints = [
        cp('a', 'A', 0, 0),
        cp('b', 'B', 10, 0),
        cp('c', 'C', 20, 0)
    ];
    const connections = [
        { edge_id: 1, source: 'A', target: 'B', origin: 'manual', edge_distance_m: 10 },
        { edge_id: 2, source: 'B', target: 'C', origin: 'manual', edge_distance_m: 10 },
        { edge_id: 3, source: 'A', target: 'C', origin: 'manual', edge_distance_m: 50 }
    ];
    const route = computeRoute({
        origin: 'a',
        destination: 'c',
        checkpoints,
        connections,
        mapConfig: flat
    });
    assert.deepEqual(route.checkpoints.map((item) => item.slug), ['a', 'b', 'c']);
    assert.equal(route.distance_m, 20);
    assert.deepEqual(route.edges.map((edge) => edge.edge_id), [1, 2]);
});

test('sentido contrário inverte os pontos e ancora no checkpoint de saída', () => {
    const trace = [{ x: 0, y: 0, t: 1 }, { x: 10, y: 2, t: 2 }, { x: 20, y: 0, t: 3 }];
    const reversed = reverseLocalPath(trace);
    assert.deepEqual(reversed.map((point) => [point.x, point.y]), [[0, 0], [-10, 2], [-20, 0]]);

    const checkpoints = [cp('a', 'A', 100, 200), cp('b', 'B', 300, 200)];
    const connections = [{
        edge_id: 7,
        reverse_edge_id: 8,
        source: 'A',
        target: 'B',
        origin: 'recorded',
        active_trace_id: 4,
        edge_distance_m: 20,
        traces: [
            { trace_id: 1, path: [{ x: 0, y: 0 }, { x: 20, y: 0 }] },
            { trace_id: 4, path: trace }
        ]
    }];
    const forward = computeRoute({
        origin: 'a',
        destination: 'b',
        checkpoints,
        connections,
        mapConfig: flat
    });
    const backward = computeRoute({
        origin: 'b',
        destination: 'a',
        checkpoints,
        connections,
        mapConfig: flat
    });
    assert.equal(forward.edges[0].direction, 'forward');
    assert.equal(backward.edges[0].direction, 'reverse');
    assert.equal(selectTracePath(connections[0])[1].y, 2);
    closeTo(forward.points, [
        { x: 100, y: 200 },
        { x: 200, y: 180 },
        { x: 300, y: 200 }
    ]);
    closeTo(backward.points, [...forward.points].reverse());
    assert.deepEqual(backward.points[0], { x: 300, y: 200 });
});

test('aresta manual sem traço é a reta entre os checkpoints', () => {
    const route = computeRoute({
        origin: 'hall',
        destination: 'copa',
        checkpoints: [cp('hall', 'Hall', 10, 10), cp('copa', 'Copa', 80, 40)],
        connections: [{
            edge_id: 3,
            source: 'Hall',
            target: 'Copa',
            origin: 'manual',
            active_trace_id: null,
            edge_distance_m: 12,
            heading_rad: Math.PI / 2,
            path: [{ x: 0, y: 0 }, { x: 0, y: 10 }, { x: 5, y: 10 }]
        }],
        mapConfig: flat
    });
    assert.equal(route.edges[0].direction, 'forward');
    closeTo(route.points, [{ x: 10, y: 10 }, { x: 80, y: 40 }]);
    assert.equal(route.distance_m, 12);
});

test('gravação sem traces usa o path e o peso distance_m', () => {
    const route = computeRoute({
        origin: 'a',
        destination: 'b',
        checkpoints: [cp('a', 'A', 0, 0), cp('b', 'B', 50, 0)],
        connections: [{
            edge_id: 1,
            source: 'A',
            target: 'B',
            origin: 'recorded',
            active_trace_id: 2,
            distance_m: 6,
            path: [{ x: 0, y: 0, t: 1 }, { x: 5, y: 0, t: 2 }]
        }],
        mapConfig: flat
    });
    assert.equal(route.distance_m, 6);
    closeTo(route.points, [{ x: 0, y: 0 }, { x: 50, y: 0 }]);
});

test('sem distância declarada, o peso é a reta em metros', () => {
    const route = computeRoute({
        origin: 'a',
        destination: 'b',
        checkpoints: [cp('a', 'A', 0, 0), cp('b', 'B', 30, 40)],
        connections: [{ edge_id: 1, source: 'A', target: 'B', origin: 'manual' }],
        mapConfig: flat
    });
    assert.equal(route.distance_m, 5);
});

test('sem caminho devolve erro tipado', () => {
    const checkpoints = [cp('a', 'A', 0, 0), cp('b', 'B', 10, 0), cp('c', 'C', 40, 0)];
    const connections = [{ edge_id: 1, source: 'A', target: 'B', origin: 'manual', edge_distance_m: 4 }];
    assert.throws(
        () => computeRoute({ origin: 'a', destination: 'c', checkpoints, connections, mapConfig: flat }),
        (error) => error instanceof RouteError && error.code === 'unreachable'
    );
    assert.throws(
        () => computeRoute({ origin: 'fantasma', destination: 'a', checkpoints, connections, mapConfig: flat }),
        (error) => error instanceof RouteError && error.code === 'unreachable'
    );
});

test('origem igual ao destino é um caminho de distância zero', () => {
    const route = computeRoute({
        origin: 'a',
        destination: 'a',
        checkpoints: [cp('a', 'Recepção', 12, 34), cp('b', 'Hall', 40, 34)],
        connections: [{ edge_id: 1, source: 'Recepção', target: 'Hall', origin: 'manual', distance_m: 8 }],
        mapConfig: flat
    });
    assert.equal(route.distance_m, 0);
    assert.deepEqual(route.checkpoints.map((item) => item.slug), ['a']);
    assert.equal(route.edges.length, 0);
    assert.deepEqual(route.points, [{ x: 12, y: 34 }]);
    assert.deepEqual(route.steps, []);
});

test('texto da prévia: 85 m a 1 m/s vira cerca de 1 minuto', () => {
    assert.equal(estimateMinutes(85), 1);
    assert.equal(estimateMinutes(90), 2);
    assert.equal(estimateMinutes(0), 0);
    assert.equal(formatDistanceLabel(85), '~85 m');
    assert.equal(formatDurationLabel(85), '~1 min');
    assert.equal(routeAnnouncement(85), 'Rota de 85 metros, cerca de 1 minuto');
    assert.equal(routeAnnouncement(90), 'Rota de 90 metros, cerca de 2 minutos');
    assert.equal(stepText('Corredor B', 20.4), 'Siga até Corredor B (~20 m)');
});

test('o enquadramento reserva a barra de cima e a busca de baixo', () => {
    assert.deepEqual(fitPadding({ top: 80, bottom: 160, inset: 24 }), {
        paddingTopLeft: [24, 104],
        paddingBottomRight: [24, 184]
    });
    const padding = chromePadding(
        { top: 100, bottom: 700 },
        {
            topRect: { top: 0, bottom: 180 },
            bottomRect: { top: 640, bottom: 760 },
            flowRect: { top: 520, bottom: 680 },
            inset: 24
        }
    );
    assert.deepEqual(padding, {
        paddingTopLeft: [24, 104],
        paddingBottomRight: [24, 204]
    });
});
