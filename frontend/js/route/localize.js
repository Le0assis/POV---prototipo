/**
 * Localização no cliente: projeção por distância acumulada na aresta calibrada
 * e leitura do checkpoint mais próximo (erro em metros na planta).
 */

import { pixelDistanceMeters } from '../map/coords.js';
import { projectByAccumulatedDistance } from './snap.js';

/** Lê tolerâncias de /api/pdr/config sem inventar constantes. */
export function readLocalization(pdr) {
    const loc = pdr && pdr.localization;
    if (!loc) return null;
    const snapEndWindowM = Number(loc.snap_end_window_m);
    const edgeMatchToleranceRad = Number(loc.edge_match_tolerance_rad);
    if (!Number.isFinite(snapEndWindowM) || !Number.isFinite(edgeMatchToleranceRad)) return null;
    return {
        method: loc.method || '',
        snapEndWindowM,
        edgeMatchToleranceRad
    };
}

/**
 * Ponto local (metros da origem) na polilinha da aresta, pela distância andada.
 * `edgeLengthM` é `edges.distance_m`: ao atingi-lo, o ponto chega no fim do path.
 */
export function projectWalk(path, walkedM, edgeLengthM) {
    return projectByAccumulatedDistance(path, walkedM, edgeLengthM);
}

/**
 * Checkpoint com pixel mais próximo do ponto projetado.
 * O erro é a distância na planta, em metros (escala uniforme).
 */
export function nearestCheckpoint(pointPx, checkpoints, pxPerM) {
    if (!pointPx || !Array.isArray(checkpoints)) return null;
    let best = null;
    checkpoints.forEach((cp) => {
        const anchor = cp && cp.anchor;
        if (!anchor) return;
        const errorM = pixelDistanceMeters(pointPx, anchor, pxPerM);
        if (errorM === null) return;
        if (!best || errorM < best.errorM) {
            best = { name: cp.name, errorM, anchor };
        }
    });
    return best;
}
