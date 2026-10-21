/**
 * Mapa do visitante: Leaflet em CRS.Simple, plano, sem rotação.
 * A planta vem de GET /api/map-config (plan_image, px_per_m).
 */

import { adaptCheckpoints } from '../core/checkpoints.js';
import { createFloorMap, resolvePlanImage } from './floor-map.js';
import { contentPixels, renderFloorLayers } from './layers.js';
import { loadFloorModel } from '../pages/floor-model.js';

export async function mountMapView(element) {
    const floor = createFloorMap(element);
    const map = floor.map;
    if (map.zoomControl) map.zoomControl.remove();
    if (map.attributionControl) map.attributionControl.remove();
    if (typeof map.touchRotate !== 'undefined' && map.touchRotate) map.touchRotate.disable();
    if (typeof map.rotate !== 'undefined' && map.rotate) map.rotate.disable();
    if (typeof map.setBearing === 'function') map.setBearing(0);

    const status = document.createElement('p');
    status.className = 'map-status';
    status.setAttribute('role', 'status');
    status.hidden = true;

    const recenter = document.createElement('button');
    recenter.type = 'button';
    recenter.className = 'btn btn-secondary map-recenter';
    recenter.textContent = 'Recentralizar';
    recenter.setAttribute('aria-label', 'Recentralizar');

    const frame = element.parentElement && element.parentElement.classList.contains('visitor-map')
        ? element.parentElement
        : element;
    frame.append(status, recenter);

    let model = {
        checkpoints: [],
        polylines: [],
        config: null
    };

    function showStatus(message) {
        status.hidden = !message;
        status.textContent = message || '';
    }

    function fit() {
        floor.fitToContent(contentPixels(model));
        map.invalidateSize();
    }

    recenter.addEventListener('click', fit);

    try {
        model = await loadFloorModel({ toast: () => {} });
    } catch (_) {
        model = { checkpoints: [], polylines: [], config: null };
    }

    model.checkpoints = adaptCheckpoints(model.checkpoints);
    const pxPerM = model.config && Number.isFinite(Number(model.config.px_per_m))
        ? Number(model.config.px_per_m)
        : null;

    if (model.config && model.config.plan_image) {
        try {
            await floor.setPlan(resolvePlanImage(model.config.plan_image));
            showStatus('');
        } catch (err) {
            showStatus(err && err.message ? err.message : 'Não foi possível carregar a planta.');
        }
    } else {
        showStatus('A planta aparece quando o mapa estiver disponível.');
    }

    renderFloorLayers(floor, model, { editable: false });
    fit();
    window.requestAnimationFrame(fit);

    return {
        floor,
        model,
        pxPerM,
        recenter: fit
    };
}
