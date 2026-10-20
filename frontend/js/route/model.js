/**
 * Normaliza o mapa, a planta e as conexões do contrato da Missão 02.
 */

import { metersToPixels } from '../map/coords.js';

export function checkpointName(node) {
    if (!node) return '';
    if (typeof node === 'string') return node;
    return String(node.name || node.id || node.label || '');
}

/** Âncora em pixels, ou null se o editor ainda não posicionou o checkpoint. 0 é válido. */
export function checkpointAnchor(node) {
    if (!node || typeof node !== 'object') return null;
    if (node.pos_x_px === null || node.pos_x_px === undefined) return null;
    if (node.pos_y_px === null || node.pos_y_px === undefined) return null;
    const x = Number(node.pos_x_px);
    const y = Number(node.pos_y_px);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return { pos_x_px: x, pos_y_px: y };
}

export function indexCheckpoints(nodes) {
    const list = (Array.isArray(nodes) ? nodes : []).map((node) => {
        const name = checkpointName(node);
        return {
            ...node,
            name,
            anchor: checkpointAnchor(node)
        };
    }).filter((node) => node.name);
    const byName = new Map(list.map((node) => [node.name, node]));
    return { list, byName };
}

/** Aceita o corpo de GET /api/map-config, com ou sem o envelope `map_config`. */
export function normalizeMapConfig(data) {
    if (!data || typeof data !== 'object') return null;
    const src = data.map_config && typeof data.map_config === 'object' ? data.map_config : data;
    const px = Number(src.px_per_m);
    const rot = Number(src.rotation_rad);
    const plan = src.plan_image == null ? '' : String(src.plan_image);
    return {
        plan_image: plan,
        px_per_m: Number.isFinite(px) ? px : null,
        rotation_rad: Number.isFinite(rot) ? rot : null,
        ready: Number.isFinite(px) && px > 0 && Number.isFinite(rot)
    };
}

/**
 * Pontos reais da gravação.
 * O PR #2 manda `path` como objeto `{ points: [{x,y,t,...}] }` (sem a origem).
 * A spec antiga manda `path` como array, já com (0, 0).
 */
export function recordedPoints(connection) {
    const raw = rawPointList(connection);
    return withOrigin(raw);
}

/** Path para desenhar: a gravação, ou a reta da aresta manual. */
export function connectionPath(connection) {
    const recorded = recordedPoints(connection);
    if (recorded.length >= 2) return recorded;
    const straight = syntheticStraight(connection);
    if (straight.length >= 2) return straight;
    return recorded;
}

export function isRecordedConnection(connection) {
    return Boolean(connection)
        && connection.origin === 'recording'
        && connection.active_trace_id != null
        && recordedPoints(connection).length >= 2;
}

/** Polilinha do process-raw, seja array ou o objeto `path.points` do PR #2. */
export function pathFromProcessResponse(data) {
    if (!data) return [];
    if (Array.isArray(data.path)) return withOrigin(data.path);
    if (data.path && Array.isArray(data.path.points)) return withOrigin(data.path.points);
    return [];
}

export function edgeIdOf(connection) {
    if (!connection) return null;
    if (connection.edge_id != null) return connection.edge_id;
    if (connection.id != null) return connection.id;
    return null;
}

/**
 * Converte cada conexão para pixels da planta.
 * Sem âncora na origem, a trajetória não é desenhada.
 * Manual (ou sem trace) sai tracejada.
 */
export function buildPolylines(connections, byName, mapConfig) {
    const polylines = [];
    const missingAnchor = [];
    (Array.isArray(connections) ? connections : []).forEach((connection) => {
        const sourceName = connection && connection.source;
        const source = byName.get(sourceName);
        const anchor = source && source.anchor;
        const path = connectionPath(connection);
        if (!anchor || !mapConfig || !mapConfig.ready) {
            missingAnchor.push(connection);
            return;
        }
        const points = [];
        path.forEach((p) => {
            const px = metersToPixels(
                { x: Number(p && p.x), y: Number(p && p.y) },
                anchor,
                mapConfig
            );
            if (px) points.push(px);
        });
        if (points.length < 2) {
            missingAnchor.push(connection);
            return;
        }
        const recorded = isRecordedConnection(connection);
        polylines.push({
            id: edgeIdOf(connection),
            source: connection.source,
            target: connection.target,
            origin: connection.origin,
            recorded,
            points,
            path,
            connection: displayConnection(connection, recorded)
        });
    });
    return { polylines, missingAnchor };
}

/** Arestas que saem de `name`, incluindo a volta sintética quando só o outro sentido veio na lista. */
export function outgoingEdges(connections, name) {
    const list = [];
    (Array.isArray(connections) ? connections : []).forEach((connection) => {
        if (!connection) return;
        if (connection.source === name) {
            list.push({
                key: `f:${edgeIdOf(connection)}`,
                edgeId: edgeIdOf(connection),
                source: connection.source,
                target: connection.target,
                headingRad: Number(connection.heading_rad),
                distanceM: Number(connection.distance_m),
                path: connectionPath(connection),
                origin: connection.origin,
                label: `${connection.source} → ${connection.target}`
            });
            return;
        }
        if (connection.target === name) {
            const path = rebaseReverse(connectionPath(connection));
            const heading = Number(connection.heading_rad);
            list.push({
                key: `r:${edgeIdOf(connection)}`,
                edgeId: connection.reverse_edge_id || edgeIdOf(connection),
                source: connection.target,
                target: connection.source,
                headingRad: Number.isFinite(heading) ? normalizeRad(heading + Math.PI) : NaN,
                distanceM: Number(connection.distance_m),
                path,
                origin: connection.origin,
                label: `${connection.target} → ${connection.source}`
            });
        }
    });
    return list.filter((edge) => edge.path.length >= 2 && Number.isFinite(edge.headingRad));
}

function displayConnection(connection, recorded) {
    const trace = traceObject(connection);
    return {
        ...connection,
        edge_id: edgeIdOf(connection),
        origin: recorded ? 'recording' : (connection.origin || 'manual'),
        steps_count: connection.steps_count ?? (trace && trace.steps_count) ?? null,
        recorded_at: connection.recorded_at
            || (trace && (trace.created_at || trace.started_at))
            || connection.updated_at
            || null,
        active_trace_id: connection.active_trace_id ?? (trace && trace.id) ?? null
    };
}

function traceObject(connection) {
    const path = connection && connection.path;
    if (path && !Array.isArray(path) && typeof path === 'object') return path;
    return null;
}

function rawPointList(connection) {
    if (!connection) return [];
    if (Array.isArray(connection.path)) return connection.path;
    const trace = traceObject(connection);
    if (trace && Array.isArray(trace.points)) return trace.points;
    const traces = Array.isArray(connection.traces) ? connection.traces : [];
    const active = traces.find((item) => item && (
        item.trace_id === connection.active_trace_id || item.id === connection.active_trace_id
    ));
    if (active && Array.isArray(active.path)) return active.path;
    if (active && Array.isArray(active.points)) return active.points;
    return [];
}

function withOrigin(points) {
    const clean = (Array.isArray(points) ? points : []).map((point) => ({
        x: Number(point && (point.x ?? point.x_m)),
        y: Number(point && (point.y ?? point.y_m)),
        t: point ? point.t : null
    })).filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
    if (clean.length === 0) return [];
    const first = clean[0];
    if (Math.abs(first.x) > 1e-6 || Math.abs(first.y) > 1e-6) {
        clean.unshift({ x: 0, y: 0, t: null });
    }
    return clean;
}

function syntheticStraight(connection) {
    const distance = Number(connection && connection.distance_m);
    const heading = Number(connection && connection.heading_rad);
    if (!Number.isFinite(distance) || distance <= 0 || !Number.isFinite(heading)) return [];
    return [
        { x: 0, y: 0, t: null },
        { x: distance * Math.cos(heading), y: distance * Math.sin(heading), t: null }
    ];
}

function rebaseReverse(path) {
    if (!Array.isArray(path) || path.length < 2) return [];
    const end = path[path.length - 1];
    const ex = Number(end && end.x);
    const ey = Number(end && end.y);
    if (!Number.isFinite(ex) || !Number.isFinite(ey)) return [];
    const reversed = [];
    for (let i = path.length - 1; i >= 0; i -= 1) {
        const x = Number(path[i] && path[i].x);
        const y = Number(path[i] && path[i].y);
        if (!Number.isFinite(x) || !Number.isFinite(y)) return [];
        reversed.push({ x: x - ex, y: y - ey, t: path[i].t });
    }
    return reversed;
}

function normalizeRad(rad) {
    const tau = Math.PI * 2;
    let r = rad % tau;
    if (r <= -Math.PI) r += tau;
    if (r > Math.PI) r -= tau;
    return r;
}
