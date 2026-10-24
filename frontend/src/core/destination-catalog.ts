/**
 * Carrega destinos da folha: o mapa atual, as categorias e a escala da planta.
 * Categoria ausente ou 404 não derruba a lista.
 */

import { getCategories, getMap, getMapConfig } from './api.js';
import { adaptCategories, adaptCheckpoints } from './checkpoints.js';
import { normalizeMapConfig } from '../route/model.js';

export async function loadDestinationCatalog(deps = {} as any) {
    const mapFn = deps.getMap || getMap;
    const categoriesFn = deps.getCategories || getCategories;
    const configFn = deps.getMapConfig || getMapConfig;

    let mapData;
    try {
        mapData = await mapFn();
    } catch (err) {
        const error = new Error('Não foi possível carregar os destinos.') as any;
        error.status = err && err.status;
        throw error;
    }

    let categories = null;
    try {
        const adapted = adaptCategories(await categoriesFn());
        categories = adapted.length ? adapted : null;
    } catch (_) {
        categories = null;
    }

    let pxPerM = null;
    try {
        const config = normalizeMapConfig(await configFn());
        const px = config && Number(config.px_per_m);
        if (Number.isFinite(px) && px > 0) pxPerM = px;
    } catch (_) {
        pxPerM = null;
    }

    const nodes = mapData && Array.isArray(mapData.nodes) ? mapData.nodes : [];
    return {
        checkpoints: adaptCheckpoints(nodes),
        categories,
        pxPerM
    };
}
