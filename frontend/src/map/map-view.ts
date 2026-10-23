/**
 * Mapa do visitante: Leaflet em CRS.Simple, plano, sem rotação.
 * A planta vem de GET /api/map-config (plan_image, px_per_m).
 */

import { adaptCheckpoints } from '../core/checkpoints.js';
import { createFloorMap, resolvePlanImage } from './floor-map.js';
import { checkpointStyle, contentPixels, createBlueDot, renderFloorLayers } from './layers.js';
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

    recenter.addEventListener('click', () => {
        if (navActive) {
            followWalker = true;
            syncRecenter();
            if (walkerPixel) panWalker(walkerPixel);
            return;
        }
        fitContent();
    });

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

    function highlight(slug, { pan = true } = {} as any) {
        const wanted = slug ? String(slug) : '';
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

    map.on('dragstart', () => {
        if (!followWalker) return;
        followWalker = false;
        syncRecenter();
    });

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
        raf(drawWalker);
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
        clearRoute,
        setNavActive,
        holdWalker,
        frameWalker,
        setWalker,
        setRouteProgress
    };
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
