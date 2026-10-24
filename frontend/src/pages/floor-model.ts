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

    const problems = [];

    if (mapResult.ok) {
        nodes = Array.isArray(mapResult.value.nodes) ? mapResult.value.nodes : [];
    } else {
        const message = failureText(mapResult.error, 'Falha ao carregar o mapa.');
        problems.push(message);
        notify(message, 'erro');
    }

    if (configResult.ok) {
        config = normalizeMapConfig(configResult.value);
    } else {
        const message = failureText(configResult.error, 'Planta ainda não configurada.');
        problems.push(message);
        notify(message, 'warn');
    }

    if (connectionResult.ok) {
        const data = connectionResult.value;
        connections = Array.isArray(data.connections) ? data.connections : [];
    } else {
        const message = failureText(connectionResult.error, 'Falha ao carregar as conexões.');
        problems.push(message);
        notify(message, 'erro');
    }

    const indexed = indexCheckpoints(nodes);
    const built = buildPolylines(connections, indexed.byName, config);
    return {
        checkpoints: indexed.list,
        byName: indexed.byName,
        config,
        connections,
        polylines: built.polylines,
        missingAnchor: built.missingAnchor,
        problems
    };
}

function failureText(error, fallback) {
    const message = error && error.message;
    return message || fallback;
}

async function settle(promise) {
    try {
        return { ok: true, value: await promise };
    } catch (error) {
        return { ok: false, error };
    }
}
