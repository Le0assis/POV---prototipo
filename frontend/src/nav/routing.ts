/**
 * Rota da prévia: Dijkstra no grafo e a polilinha em pixels da planta.
 * Aresta gravada usa o traço ativo (ou o primeiro). No sentido contrário,
 * os pontos são invertidos e ancorados no checkpoint de saída.
 * Aresta manual, ou sem traço, vira o segmento reto entre os checkpoints.
 */

import { metersToPixels } from '../map/units.js';
import {
    RouteError,
    anchorOf,
    buildGraph,
    findCheckpoint,
    shortestPath
} from './graph.js';

export { RouteError };

export const WALK_SPEED_MPS = 1;

export function planRoute(input) {
    try {
        return { ok: true, route: computeRoute(input) };
    } catch (error) {
        if (error instanceof RouteError) return { ok: false, error };
        throw error;
    }
}

export function computeRoute({ origin, destination, checkpoints, connections, mapConfig } = {} as any) {
    const list = Array.isArray(checkpoints) ? checkpoints : [];
    const from = findCheckpoint(list, origin);
    const to = findCheckpoint(list, destination);
    if (!from || !to) throw new RouteError('unreachable');

    const config = flatConfig(mapConfig);
    const graph = buildGraph(list, connections, config);
    const path = shortestPath(graph.adj, from.slug, to.slug);
    const ordered = path.nodes.map((slug) => graph.nodes.get(slug));
    const edges = [];
    const points = [];

    if (!path.edges.length) {
        const alone = anchorOf(from);
        if (alone) points.push({ x: alone.pos_x_px, y: alone.pos_y_px });
    }

    path.edges.forEach((edge) => {
        const source = graph.nodes.get(edge.from);
        const target = graph.nodes.get(edge.to);
        const geometry = edgePixels(edge, source, target, config);
        if (!geometry || geometry.length < 2) throw new RouteError('unreachable');
        edges.push({
            edge_id: edge.edge_id,
            reverse_edge_id: edge.reverse_edge_id,
            direction: edge.direction,
            distance_m: edge.weight,
            from: publishCheckpoint(source),
            to: publishCheckpoint(target),
            points: geometry
        });
        appendPoints(points, geometry);
    });

    const distance = path.distance;
    return {
        checkpoints: ordered.map(publishCheckpoint),
        edges,
        distance_m: distance,
        points,
        summary: describeRoute(distance),
        steps: edges.map((edge) => ({
            slug: edge.to.slug,
            distance_m: edge.distance_m,
            text: stepText(edge.to.name, edge.distance_m)
        }))
    };
}

/** Traço ativo, senão o primeiro. Sem `traces`, a gravação usa `path`. */
export function selectTracePath(connection) {
    if (!connection) return null;
    const traces = Array.isArray(connection.traces) ? connection.traces : [];
    if (traces.length) {
        const activeId = connection.active_trace_id;
        const active = activeId == null
            ? null
            : traces.find((trace) => String(trace.trace_id ?? trace.id) === String(activeId));
        const chosen = active || traces[0];
        const path = finitePoints(chosen && chosen.path);
        if (path.length >= 2) return path;
    }
    if (connection.origin === 'recorded') {
        const path = finitePoints(connection.path);
        if (path.length >= 2) return path;
    }
    return null;
}

/**
 * Inverte o traço e o reancora em (0, 0) no fim original,
 * que passa a ser o checkpoint de saída.
 */
export function reverseLocalPath(path) {
    const points = finitePoints(path);
    if (points.length < 2) return [];
    const end = points[points.length - 1];
    const reversed = [];
    for (let i = points.length - 1; i >= 0; i -= 1) {
        reversed.push({
            x: points[i].x - end.x,
            y: points[i].y - end.y,
            t: points[i].t
        });
    }
    return reversed;
}

export function estimateMinutes(distanceM, speedMps = WALK_SPEED_MPS) {
    if (!Number.isFinite(distanceM) || distanceM <= 0) return 0;
    const rounded = Math.round((distanceM / speedMps) / 60);
    return Math.max(1, rounded);
}

export function formatDistanceLabel(meters) {
    if (!Number.isFinite(meters)) return '';
    return `~${Math.round(meters)} m`;
}

export function formatDurationLabel(distanceM, speedMps = WALK_SPEED_MPS) {
    const minutes = estimateMinutes(distanceM, speedMps);
    return `~${minutes} min`;
}

export function routeAnnouncement(distanceM, speedMps = WALK_SPEED_MPS) {
    const meters = Math.max(0, Math.round(Number(distanceM) || 0));
    const minutes = estimateMinutes(distanceM, speedMps);
    const meterWord = meters === 1 ? 'metro' : 'metros';
    const minuteWord = minutes === 1 ? 'minuto' : 'minutos';
    return `Rota de ${meters} ${meterWord}, cerca de ${minutes} ${minuteWord}`;
}

export function stepText(name, distanceM) {
    return `Siga até ${name} (${formatDistanceLabel(distanceM)})`;
}

export function describeRoute(distanceM, speedMps = WALK_SPEED_MPS) {
    return {
        distance_m: distanceM,
        minutes: estimateMinutes(distanceM, speedMps),
        distanceLabel: formatDistanceLabel(distanceM),
        timeLabel: formatDurationLabel(distanceM, speedMps),
        announcement: routeAnnouncement(distanceM, speedMps)
    };
}

function edgePixels(edge, from, to, mapConfig) {
    const trace = recordedTrace(edge.connection);
    if (trace) {
        const local = edge.direction === 'reverse' ? reverseLocalPath(trace) : trace;
        const anchor = anchorOf(from);
        if (anchor && local.length >= 2) {
            const pixels = local
                .map((point) => metersToPixels(point, anchor, mapConfig))
                .filter(Boolean);
            if (pixels.length >= 2) return pixels;
        }
    }
    const start = anchorOf(from);
    const end = anchorOf(to);
    if (!start || !end) return null;
    return [
        { x: start.pos_x_px, y: start.pos_y_px },
        { x: end.pos_x_px, y: end.pos_y_px }
    ];
}

function recordedTrace(connection) {
    if (!connection || connection.origin === 'manual') return null;
    const trace = selectTracePath(connection);
    if (!trace && connection.origin !== 'recorded') return null;
    return trace;
}

function publishCheckpoint(checkpoint) {
    const anchor = anchorOf(checkpoint);
    const name = String(checkpoint.name || checkpoint.label || checkpoint.slug);
    return {
        slug: String(checkpoint.slug),
        name,
        label: name,
        pos_x_px: anchor ? anchor.pos_x_px : null,
        pos_y_px: anchor ? anchor.pos_y_px : null
    };
}

function appendPoints(all, next) {
    next.forEach((point, index) => {
        if (index === 0 && all.length) {
            const last = all[all.length - 1];
            if (Math.abs(last.x - point.x) < 0.01 && Math.abs(last.y - point.y) < 0.01) return;
        }
        all.push({ x: point.x, y: point.y });
    });
}

function finitePoints(path) {
    if (!Array.isArray(path)) return [];
    return path.map((point) => ({
        x: Number(point && point.x),
        y: Number(point && point.y),
        t: point ? point.t : null
    })).filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
}

function flatConfig(mapConfig) {
    const src = mapConfig && mapConfig.map_config ? mapConfig.map_config : (mapConfig || {});
    return {
        px_per_m: src.px_per_m,
        rotation_rad: src.rotation_rad
    };
}
