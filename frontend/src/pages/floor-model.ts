/**
 * Carrega mapa, planta e conexões em paralelo. Falha de um GET não apaga o que já veio.
 */

import { getConnections, getMap, getMapConfig } from '../core/api.js';
import {
    indexCheckpoints,
    normalizeMapConfig,
    buildPolylines
} from '../route/model.js';

export async function loadFloorModel({ toast, includePath = true, api } = {} as any) {
    const notify = typeof toast === 'function' ? toast : () => {};
    const client = api || { getMap, getMapConfig, getConnections };
    const [mapResult, configResult, connectionResult] = await Promise.all([
        settle(client.getMap()),
        settle(client.getMapConfig()),
        settle(client.getConnections({ includePath }))
    ]);

    let nodes = [];
    let config = null;
    let connections = [];

    if (mapResult.ok) {
        nodes = Array.isArray(mapResult.value.nodes) ? mapResult.value.nodes : [];
    } else {
        notify(mapResult.error.message || 'Falha ao carregar o mapa.', 'erro');
    }

    if (configResult.ok) {
        config = normalizeMapConfig(configResult.value);
    } else {
        notify(configResult.error.message || 'Planta ainda não configurada.', 'warn');
    }

    if (connectionResult.ok) {
        const data = connectionResult.value;
        connections = Array.isArray(data.connections) ? data.connections : [];
    } else {
        notify(connectionResult.error.message || 'Falha ao carregar as conexões.', 'erro');
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

async function settle(promise) {
    try {
        return { ok: true, value: await promise };
    } catch (error) {
        return { ok: false, error };
    }
}
