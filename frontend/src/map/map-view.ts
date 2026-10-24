/**
 * Mapa do visitante: Leaflet em CRS.Simple, plano, sem rotação.
 * A planta vem de GET /api/map-config (plan_image, px_per_m).
 */

import { adaptCheckpoints } from '../core/checkpoints.js';
import { createFloorMap, resolvePlanImage } from './floor-map.js';
import { checkpointStyle, contentPixels, createBlueDot, renderFloorLayers } from './layers.js';
import { floorNotice, mountMapStatus } from './map-status.js';
import { chromePadding, createRouteLayer } from './route-layer.js';
import { loadFloorModel } from '../pages/floor-model.js';

export async function mountMapView(element) {
    if (element && element._povMapView && typeof element._povMapView.destroy === 'function') {
        element._povMapView.destroy();
    }
    const frame = element.parentElement && element.parentElement.classList.contains('visitor-map')
        ? element.parentElement
        : element;
    const status = mountMapStatus(frame);
    let floor;
    try {
        floor = createFloorMap(element);
    } catch (err) {
        status.show(err && err.message ? err.message : 'Não foi possível abrir o mapa.', {
            error: true,
            host: element
        });
        throw err;
    }
    const map = floor.map;
    if (map.zoomControl && typeof map.zoomControl.setPosition === 'function') {
        map.zoomControl.setPosition('bottomleft');
    }
    if (map.attributionControl) map.attributionControl.remove();
    if (typeof map.touchRotate !== 'undefined' && map.touchRotate) map.touchRotate.disable();
    if (typeof map.rotate !== 'undefined' && map.rotate) map.rotate.disable();
    if (typeof map.setBearing === 'function') map.setBearing(0);

    const recenter = document.createElement('button');
    recenter.type = 'button';
    recenter.className = 'btn btn-secondary map-recenter';
    recenter.textContent = 'Recentralizar';
    recenter.setAttribute('aria-label', 'Recentralizar');

    frame.append(recenter);

    const model = {
        checkpoints: [],
        polylines: [],
        config: null,
        connections: [],
        problems: [],
        byName: null,
        missingAnchor: []
    };
    let destroyed = false;
    let loadGen = 0;
    let view = null;

    function scaleOf() {
        const scale = model.config && Number(model.config.px_per_m);
        return Number.isFinite(scale) ? scale : null;
    }

    function adopt(next) {
        model.checkpoints = adaptCheckpoints(next && next.checkpoints);
        model.polylines = (next && next.polylines) || [];
        model.config = (next && next.config) || null;
        model.connections = (next && next.connections) || [];
        model.byName = next && next.byName;
        model.missingAnchor = next && next.missingAnchor;
        model.problems = (next && next.problems) || [];
        if (view) view.pxPerM = scaleOf();
    }

    function paintNotice(planError) {
        if (destroyed) return;
        const notice = floorNotice(model, planError);
        status.show(notice.message, {
            error: notice.error,
            host: element,
            onRetry: notice.retry ? () => { void loadMap(); } : null
        });
    }

    async function loadMap() {
        const gen = ++loadGen;
        status.show('Carregando o mapa…', { busy: true, host: element });
        const next = await loadFloorModel({ toast: () => {} });
        if (destroyed || gen !== loadGen) return null;
        adopt(next);
        let planError = '';
        if (model.config && model.config.plan_image) {
            try {
                await floor.setPlan(resolvePlanImage(model.config.plan_image));
            } catch (err) {
                planError = err && err.message ? err.message : 'Não foi possível carregar a planta.';
            }
        } else if (typeof floor.clearPlan === 'function') {
            floor.clearPlan();
        }
        if (destroyed || gen !== loadGen) return null;
        renderFloorLayers(floor, model, { editable: false });
        tagCheckpointMarkers(floor, model.checkpoints);
        paintNotice(planError);
        return model;
    }

    recenter.addEventListener('click', onRecenter);
    function onRecenter() {
        if (navActive) {
            followWalker = true;
            syncRecenter();
            if (walkerPixel) panWalker(walkerPixel);
            return;
        }
        fitContent();
    }

    await loadMap();

    const routeLayer = createRouteLayer(floor);
    floor.onLayers = (layers) => {
        floor.layers = layers || floor.layers;
        routeLayer.setVisible(!layers || layers.route !== false);
    };
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

    function highlight(slug, { pan = true } = {} as any) {
        const wanted = slug ? String(slug) : '';
        floor.labelFocus = floor.labelFocus || { origin: '', destination: '' };
        floor.labelFocus.destination = wanted;
        if (typeof floor.syncLabels === 'function') floor.syncLabels();
        let target = null;
        floor.checkpoints.eachLayer((marker) => {
            const on = Boolean(wanted) && marker.checkpointSlug === wanted;
            const el = typeof marker.getElement === 'function' ? marker.getElement() : null;
            if (el) el.classList.toggle('is-destination', on);
            if (typeof marker.setStyle === 'function') marker.setStyle(checkpointStyle(on));
            if (typeof marker.setZIndexOffset === 'function') marker.setZIndexOffset(on ? 700 : 0);
            if (on) target = marker;
        });
        if (target && pan && typeof target.getLatLng === 'function') {
            floor.map.panTo(target.getLatLng(), { animate: false });
        }
    }

    function showRoute(route, { fit = true, markOrigin = true } = {} as any) {
        routeActive = true;
        routeLayer.show(route, { markOrigin });
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
    let walker = null;
    let followWalker = false;
    let navActive = false;
    let walkerPixel = null;
    const pins = new Map();

    function onDragStart() {
        if (!followWalker) return;
        followWalker = false;
        syncRecenter();
    }
    map.on('dragstart', onDragStart);

    function syncRecenter() {
        recenter.classList.toggle('needs-recenter', navActive && !followWalker);
    }

    function ensureWalker() {
        if (!walker) {
            walker = createBlueDot(floor, { label: 'você', cone: true, zIndex: 1200 });
            if (floor.locateLayer && typeof floor.locateLayer.bringToFront === 'function') {
                floor.locateLayer.bringToFront();
            }
        }
        return walker;
    }

    function panWalker(pixel) {
        panIfOutside(pixel, true);
    }

    function panIfOutside(pixel, force) {
        if (!pixel) return;
        const latlng = floor.pixelToLatLng(pixel.x, pixel.y);
        if (force) {
            map.panTo(latlng, { animate: false });
            return;
        }
        const size = map.getSize();
        if (!size || !size.x || !size.y) return;
        const point = map.latLngToContainerPoint(latlng);
        const marginX = size.x * 0.28;
        const marginY = size.y * 0.28;
        const inside = point.x >= marginX && point.y >= marginY
            && point.x <= size.x - marginX && point.y <= size.y - marginY;
        if (!inside) map.panTo(latlng, { animate: false });
    }

    function setNavActive(on) {
        navActive = Boolean(on);
        if (!navActive) {
            followWalker = false;
            walkerPixel = null;
            if (walker) walker.hide();
        }
        syncRecenter();
    }

    /** Chegada: para de seguir, mas o marcador fica onde a caminhada terminou. */
    function holdWalker() {
        followWalker = false;
        navActive = false;
        syncRecenter();
    }

    function frameWalker(pixel, pxPerM) {
        if (!pixel) return;
        walkerPixel = { x: pixel.x, y: pixel.y };
        const scale = Number(pxPerM);
        const radius = (Number.isFinite(scale) && scale > 0 ? scale : 10) * 18;
        followWalker = true;
        syncRecenter();
        const bounds = L.latLngBounds(
            floor.pixelToLatLng(pixel.x - radius, pixel.y - radius),
            floor.pixelToLatLng(pixel.x + radius, pixel.y + radius)
        );
        map.fitBounds(bounds, { padding: [28, 28], animate: false, maxZoom: 2 });
        if (floor.locateLayer && typeof floor.locateLayer.bringToFront === 'function') {
            floor.locateLayer.bringToFront();
        }
    }

    let shownWalker = null;
    let shownHeading = null;
    let walkerTarget = null;
    let walkerQueued = false;
    let walkerFrame = 0;

    function setWalker(pixel, screenDeg) {
        if (!pixel || !Number.isFinite(pixel.x) || !Number.isFinite(pixel.y)) {
            walkerPixel = null;
            walkerTarget = null;
            shownWalker = null;
            shownHeading = null;
            if (walker) walker.hide();
            return;
        }
        walkerTarget = {
            x: pixel.x,
            y: pixel.y,
            heading: Number.isFinite(screenDeg) ? screenDeg : null
        };
        if (walkerQueued) return;
        walkerQueued = true;
        const raf = typeof window.requestAnimationFrame === 'function'
            ? window.requestAnimationFrame.bind(window)
            : (fn) => fn();
        walkerFrame = raf(drawWalker) || 0;
    }

    function drawWalker() {
        walkerQueued = false;
        const target = walkerTarget;
        if (!target) return;
        if (!shownWalker) shownWalker = { x: target.x, y: target.y };
        else {
            shownWalker = {
                x: shownWalker.x + (target.x - shownWalker.x) * 0.45,
                y: shownWalker.y + (target.y - shownWalker.y) * 0.45
            };
        }
        if (target.heading != null) {
            shownHeading = shownHeading == null
                ? target.heading
                : lerpDegrees(shownHeading, target.heading, 0.45);
        }
        walkerPixel = { x: shownWalker.x, y: shownWalker.y };
        const dot = ensureWalker();
        dot.setPixel(shownWalker.x, shownWalker.y);
        if (shownHeading != null) dot.setHeading(shownHeading);
        if (followWalker) panIfOutside(shownWalker, false);
        const left = Math.hypot(target.x - shownWalker.x, target.y - shownWalker.y);
        if (left > 0.6) setWalker(target, target.heading);
    }

    function setRouteProgress(fraction) {
        if (routeLayer && typeof routeLayer.setProgress === 'function') routeLayer.setProgress(fraction);
    }

    function showOrigin(slug, anchor) {
        const wanted = slug ? String(slug) : '';
        floor.labelFocus = floor.labelFocus || { origin: '', destination: '' };
        floor.labelFocus.origin = wanted;
        if (typeof floor.syncLabels === 'function') floor.syncLabels();
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

    function destroy() {
        if (destroyed) return;
        destroyed = true;
        if (walkerFrame && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(walkerFrame);
        recenter.removeEventListener('click', onRecenter);
        if (typeof map.off === 'function') map.off('dragstart', onDragStart);
        recenter.remove();
        status.destroy();
        if (routeLayer && typeof routeLayer.destroy === 'function') routeLayer.destroy();
        if (floor && typeof floor.destroy === 'function') floor.destroy();
        if (element && element._povMapView === view) delete element._povMapView;
    }

    view = {
        floor,
        model,
        pxPerM: scaleOf(),
        recenter: fitContent,
        highlight,
        showOrigin,
        showRoute,
        clearRoute,
        setNavActive,
        holdWalker,
        frameWalker,
        setWalker,
        setRouteProgress,
        destroy
    };
    if (element) element._povMapView = view;
    return view;
}

function lerpDegrees(from, to, amount) {
    const delta = ((to - from + 540) % 360) - 180;
    return from + delta * amount;
}

function tagCheckpointMarkers(floor, checkpoints) {
    const placed = (Array.isArray(checkpoints) ? checkpoints : []).filter((cp) => cp && cp.anchor);
    const byName = new Map(placed.map((cp) => [cp.name, cp]));
    floor.checkpoints.getLayers().forEach((marker, index) => {
        const cp = byName.get(marker.checkpointName) || placed[index];
        if (!cp) return;
        marker.checkpointSlug = String(cp.slug || cp.name || '');
    });
}
