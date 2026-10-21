/**
 * Mapa do visitante: Leaflet em CRS.Simple, plano, sem rotação.
 * A planta vem de GET /api/map-config (plan_image, px_per_m).
 */

import { adaptCheckpoints } from '../core/checkpoints.js';
import { createFloorMap, resolvePlanImage } from './floor-map.js';
import { contentPixels, createBlueDot, renderFloorLayers } from './layers.js';
import { chromePadding, createRouteLayer } from './route-layer.js';
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

    recenter.addEventListener('click', fitContent);

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
    tagCheckpointMarkers(floor, model.checkpoints);
    const routeLayer = createRouteLayer(floor);
    let routeActive = false;

    function fitContent() {
        map.invalidateSize();
        if (routeActive) {
            routeLayer.fit(routePadding());
            return;
        }
        floor.fitToContent(contentPixels(model));
    }

    fitContent();
    window.requestAnimationFrame(fitContent);

    function routePadding() {
        const mapRect = element.getBoundingClientRect();
        const shell = element.closest('.visitor-shell');
        const top = shell && shell.querySelector('.visitor-top');
        const bottom = shell && shell.querySelector('.visitor-bottom');
        const panel = document.getElementById('visitor-flow');
        return chromePadding(mapRect, {
            topRect: top ? top.getBoundingClientRect() : null,
            bottomRect: bottom ? bottom.getBoundingClientRect() : null,
            flowRect: panel && !panel.hidden ? panel.getBoundingClientRect() : null
        });
    }

    function highlight(slug, { pan = true } = {}) {
        const wanted = slug ? String(slug) : '';
        let target = null;
        floor.checkpoints.eachLayer((marker) => {
            const on = Boolean(wanted) && marker.checkpointSlug === wanted;
            const el = marker.getElement();
            if (el) el.classList.toggle('is-destination', on);
            if (typeof marker.setZIndexOffset === 'function') marker.setZIndexOffset(on ? 700 : 0);
            if (on) target = marker;
        });
        if (target && pan) floor.map.panTo(target.getLatLng(), { animate: false });
    }

    function showRoute(route, { fit = true } = {}) {
        routeActive = true;
        routeLayer.show(route);
        if (!fit) return;
        const apply = () => {
            if (routeActive) routeLayer.fit(routePadding());
        };
        apply();
        if (typeof window.requestAnimationFrame === 'function') {
            window.requestAnimationFrame(() => window.requestAnimationFrame(apply));
        }
    }

    function clearRoute() {
        routeActive = false;
        routeLayer.clear();
    }

    let you = null;
    let youSlug = '';
    const pins = new Map();

    function showOrigin(slug, anchor) {
        const wanted = slug ? String(slug) : '';
        if (!you) you = createBlueDot(floor, { label: 'você' });
        if (wanted && anchor && Number.isFinite(Number(anchor.pos_x_px)) && Number.isFinite(Number(anchor.pos_y_px))) {
            pins.set(wanted, { pos_x_px: Number(anchor.pos_x_px), pos_y_px: Number(anchor.pos_y_px) });
        }
        const placed = model.checkpoints.find((cp) => cp && (cp.slug === wanted || cp.name === wanted));
        const point = (placed && placed.anchor) || pins.get(wanted) || null;
        if (!wanted || !point) {
            you.hide();
            youSlug = '';
            return;
        }
        you.setPixel(point.pos_x_px, point.pos_y_px);
        if (youSlug !== wanted) {
            const latlng = floor.pixelToLatLng(point.pos_x_px, point.pos_y_px);
            map.setView(latlng, map.getZoom(), { animate: false });
            youSlug = wanted;
        }
    }

    return {
        floor,
        model,
        pxPerM,
        recenter: fitContent,
        highlight,
        showOrigin,
        showRoute,
        clearRoute
    };
}

function tagCheckpointMarkers(floor, checkpoints) {
    const placed = (Array.isArray(checkpoints) ? checkpoints : []).filter((cp) => cp && cp.anchor);
    floor.checkpoints.getLayers().forEach((marker, index) => {
        const cp = placed[index];
        marker.checkpointSlug = cp ? String(cp.slug || cp.name || '') : '';
    });
}
