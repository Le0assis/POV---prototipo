/**
 * Carrega mapa, planta e conexões. Falha de um GET não apaga o que já veio.
 */

import { getConnections, getMap, getMapConfig } from '../core/api.js';
import {
    indexCheckpoints,
    normalizeMapConfig,
    buildPolylines
} from '../route/model.js';

export async function loadFloorModel({ toast } = {}) {
    const notify = typeof toast === 'function' ? toast : () => {};
    let nodes = [];
    let config = null;
    let connections = [];

    try {
        const mapData = await getMap();
        nodes = Array.isArray(mapData.nodes) ? mapData.nodes : [];
    } catch (err) {
        notify(err.message || 'Falha ao carregar o mapa.', 'erro');
    }

    try {
        config = normalizeMapConfig(await getMapConfig());
    } catch (err) {
        notify(err.message || 'Planta ainda não configurada.', 'warn');
    }

    try {
        const data = await getConnections({ includePath: true });
        connections = Array.isArray(data.connections) ? data.connections : [];
    } catch (err) {
        notify(err.message || 'Falha ao carregar as conexões.', 'erro');
    }

    const indexed = indexCheckpoints(nodes);
    const built = buildPolylines(connections, indexed.byName, config);
    return {
        checkpoints: indexed.list,
        byName: indexed.byName,
        config,
        connections,
        polylines: built.polylines,
        missingAnchor: built.missingAnchor
    };
}
