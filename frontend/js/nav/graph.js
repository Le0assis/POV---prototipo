/**
 * Grafo não dirigido dos checkpoints.
 * Cada conexão física vale nos dois sentidos. O peso é `edge_distance_m`
 * (ou `distance_m`, o nome do GET /api/connections). Sem distância declarada,
 * cai na reta entre as âncoras, em metros.
 */

export const UNREACHABLE_MESSAGE = 'Não encontramos um caminho entre esses pontos';

export class RouteError extends Error {
    constructor(code, message) {
        super(message || UNREACHABLE_MESSAGE);
        this.name = 'RouteError';
        this.code = code;
    }
}

export function anchorOf(checkpoint) {
    if (!checkpoint || typeof checkpoint !== 'object') return null;
    const nested = checkpoint.anchor;
    const x = numberOr(checkpoint.pos_x_px, nested && nested.pos_x_px);
    const y = numberOr(checkpoint.pos_y_px, nested && nested.pos_y_px);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return { pos_x_px: x, pos_y_px: y };
}

export function findCheckpoint(checkpoints, key) {
    const wanted = String(key || '').trim();
    if (!wanted) return null;
    return (Array.isArray(checkpoints) ? checkpoints : []).find((cp) => {
        if (!cp) return false;
        return cp.slug === wanted || cp.name === wanted || String(cp.id || '') === wanted;
    }) || null;
}

/**
 * @returns {{ nodes: Map<string, object>, adj: Map<string, object[]> }}
 */
export function buildGraph(checkpoints, connections, mapConfig) {
    const nodes = new Map();
    (Array.isArray(checkpoints) ? checkpoints : []).forEach((cp) => {
        if (!cp || !cp.slug) return;
        nodes.set(String(cp.slug), cp);
    });
    const adj = new Map();
    nodes.forEach((_, slug) => adj.set(slug, []));

    (Array.isArray(connections) ? connections : []).forEach((connection) => {
        if (!connection) return;
        const source = findCheckpoint(checkpoints, connection.source || connection.source_node);
        const target = findCheckpoint(checkpoints, connection.target || connection.target_node);
        if (!source || !target || source.slug === target.slug) return;
        const weight = edgeWeight(connection, source, target, mapConfig);
        if (!Number.isFinite(weight) || weight < 0) return;
        const shared = {
            weight,
            connection,
            edge_id: connection.edge_id ?? null,
            reverse_edge_id: connection.reverse_edge_id ?? null
        };
        adj.get(source.slug).push({
            ...shared,
            from: source.slug,
            to: target.slug,
            direction: 'forward'
        });
        adj.get(target.slug).push({
            ...shared,
            from: target.slug,
            to: source.slug,
            direction: 'reverse'
        });
    });

    return { nodes, adj };
}

/** Dijkstra. Origem igual ao destino devolve um caminho de um nó e distância 0. */
export function shortestPath(adj, start, end) {
    if (!adj || !adj.has(start) || !adj.has(end)) {
        throw new RouteError('unreachable', UNREACHABLE_MESSAGE);
    }
    if (start === end) return { nodes: [start], edges: [], distance: 0 };

    const dist = new Map([[start, 0]]);
    const prev = new Map();
    const pending = new Set(adj.keys());

    while (pending.size) {
        let current = null;
        let best = Infinity;
        pending.forEach((node) => {
            const value = dist.has(node) ? dist.get(node) : Infinity;
            if (value < best) {
                best = value;
                current = node;
            }
        });
        if (current == null || best === Infinity) break;
        pending.delete(current);
        if (current === end) break;
        (adj.get(current) || []).forEach((edge) => {
            if (!pending.has(edge.to)) return;
            const next = best + edge.weight;
            const known = dist.has(edge.to) ? dist.get(edge.to) : Infinity;
            if (next < known) {
                dist.set(edge.to, next);
                prev.set(edge.to, edge);
            }
        });
    }

    if (!prev.has(end) || !Number.isFinite(dist.get(end))) {
        throw new RouteError('unreachable', UNREACHABLE_MESSAGE);
    }

    const nodes = [end];
    const edges = [];
    let cursor = end;
    while (cursor !== start) {
        const edge = prev.get(cursor);
        if (!edge) throw new RouteError('unreachable', UNREACHABLE_MESSAGE);
        edges.push(edge);
        cursor = edge.from;
        nodes.push(cursor);
    }
    edges.reverse();
    nodes.reverse();
    return { nodes, edges, distance: dist.get(end) };
}

export function edgeWeight(connection, from, to, mapConfig) {
    const declared = firstFinite(connection && connection.edge_distance_m, connection && connection.distance_m);
    if (declared != null && declared >= 0) return declared;
    return straightMeters(from, to, mapConfig);
}

function straightMeters(from, to, mapConfig) {
    const scale = scaleOf(mapConfig);
    const a = anchorOf(from);
    const b = anchorOf(to);
    if (!a || !b || scale == null) return null;
    return Math.hypot(a.pos_x_px - b.pos_x_px, a.pos_y_px - b.pos_y_px) / scale;
}

function scaleOf(mapConfig) {
    const src = mapConfig && mapConfig.map_config ? mapConfig.map_config : mapConfig;
    const scale = Number(src && src.px_per_m);
    return Number.isFinite(scale) && scale > 0 ? scale : null;
}

function firstFinite(...values) {
    for (let i = 0; i < values.length; i += 1) {
        if (values[i] == null || values[i] === '') continue;
        const number = Number(values[i]);
        if (Number.isFinite(number)) return number;
    }
    return null;
}

function numberOr(primary, fallback) {
    if (primary != null && primary !== '') {
        const number = Number(primary);
        if (Number.isFinite(number)) return number;
    }
    if (fallback == null || fallback === '') return NaN;
    return Number(fallback);
}
