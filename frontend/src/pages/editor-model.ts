/**
 * Atualiza o modelo do editor com a resposta de um salvamento.
 * Não busca o mapa de novo.
 */

import { buildPolylines, checkpointAnchor } from '../route/model.js';

export function patchCheckpointPosition(model, name, pixel) {
    const node = model && model.byName && model.byName.get(name);
    if (!node || !pixel) return false;
    node.pos_x_px = pixel.pos_x_px;
    node.pos_y_px = pixel.pos_y_px;
    node.anchor = checkpointAnchor(node);
    refreshPolylines(model);
    return true;
}

export function addCheckpoint(model, raw) {
    const name = raw && (raw.name || raw.label);
    if (!model || !name) return null;
    if (model.byName && model.byName.has(name)) return model.byName.get(name);
    const node = {
        ...raw,
        name: String(name),
        anchor: checkpointAnchor(raw)
    };
    model.checkpoints.push(node);
    model.byName.set(node.name, node);
    return node;
}

/** Uma conexão no formato do GET /api/connections (o par, não os dois sentidos). */
export function addManualConnection(model, edge) {
    if (!model || !edge || !edge.source || !edge.target) return null;
    const heading = Number(edge.heading_rad) || 0;
    const distance = Number(edge.distance_m);
    const connection = {
        source: edge.source,
        target: edge.target,
        distance_m: distance,
        heading_rad: heading,
        origin: 'manual',
        path: straightPath(distance, heading)
    };
    model.connections.push(connection);
    refreshPolylines(model);
    return connection;
}

function refreshPolylines(model) {
    const built = buildPolylines(model.connections, model.byName, model.config);
    model.polylines = built.polylines;
    model.missingAnchor = built.missingAnchor;
}

function straightPath(distance, heading) {
    const length = Number.isFinite(distance) ? distance : 0;
    return [
        { x: 0, y: 0, t: null },
        { x: length * Math.cos(heading), y: length * Math.sin(heading), t: null }
    ];
}
