/**
 * Mapa só de leitura. Nenhum controle grava checkpoint, conexão ou posição.
 */

import { insertTopNav } from '../components/nav.js';
import { $ } from '../core/dom.js';
import { toast } from '../core/toast.js';
import { createFloorMap, resolvePlanImage } from '../map/floor-map.js';
import { renderFloorLayers, contentPixels } from '../map/layers.js';
import { loadFloorModel } from './floor-model.js';

if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', init);
}

export function viewerNote(model) {
    const hidden = model && Array.isArray(model.missingAnchor) ? model.missingAnchor.length : 0;
    const manual = ((model && model.polylines) || []).filter((poly) => poly && poly.recorded === false);
    const parts = [];
    if (hidden) {
        parts.push(`${hidden} conexão(ões) sem trajetória desenhada: checkpoint de origem sem posição na planta.`);
    }
    if (manual.length) {
        const names = manual.map((poly) => `${poly.source} → ${poly.target}`).join(', ');
        parts.push(`Arestas manuais: ${names}.`);
    }
    return parts.join(' ');
}

async function init() {
    insertTopNav('viewer');
    const floor = createFloorMap($('#floor-map'));
    const model = await loadFloorModel({ toast });
    if (model.config && model.config.plan_image) {
        try {
            await floor.setPlan(resolvePlanImage(model.config.plan_image));
        } catch (err) {
            toast(err.message || 'Planta indisponível.', 'warn');
        }
    }
    renderFloorLayers(floor, model, { editable: false, showManual: true });
    floor.fitToContent(contentPixels(model));
    $('#viewer-note').textContent = viewerNote(model);
}
