/**
 * Mapa só de leitura. Nenhum controle grava checkpoint, conexão ou posição.
 */

import { insertTopNav } from '../components/nav.js';
import { $ } from '../core/dom.js';
import { toast } from '../ui/toast.js';
import { createFloorMap, resolvePlanImage } from '../map/floor-map.js';
import { renderFloorLayers, contentPixels } from '../map/layers.js';
import { loadFloorModel } from './floor-model.js';

document.addEventListener('DOMContentLoaded', init);

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
    renderFloorLayers(floor, model, { editable: false });
    floor.fitToContent(contentPixels(model));
    const hidden = model.missingAnchor.length;
    $('#viewer-note').textContent = hidden
        ? `${hidden} conexão(ões) sem trajetória desenhada: checkpoint de origem sem posição na planta.`
        : '';
}
