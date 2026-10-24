/**
 * Mapa Leaflet em L.CRS.Simple: planta como imageOverlay, plano, sem inclinação.
 * Coordenadas de desenho são pixels da imagem (origem no canto superior esquerdo, y para baixo).
 */

import { mountLayerControls } from './layer-controls.js';
import { attachPerf } from './perf.js';
import { readLayerVisibility } from './style.js';

function coarsePointer() {
    try {
        return typeof window !== 'undefined'
            && typeof window.matchMedia === 'function'
            && window.matchMedia('(pointer: coarse)').matches;
    } catch (_) {
        return false;
    }
}

export function createFloorMap(element) {
    if (element && element._povFloor && typeof element._povFloor.destroy === 'function') {
        element._povFloor.destroy();
    }
    if (typeof L === 'undefined') {
        throw new Error('Leaflet não carregou.');
    }
    const coarse = coarsePointer();
    const renderer = L.canvas({ padding: 0.5, tolerance: coarse ? 10 : 0 });
    const map = L.map(element, {
        crs: L.CRS.Simple,
        preferCanvas: true,
        renderer,
        minZoom: -4,
        maxZoom: 4,
        zoomSnap: 0.25,
        attributionControl: true,
        bounceAtZoomLimits: false,
        zoomAnimation: !coarse,
        fadeAnimation: false,
        markerZoomAnimation: !coarse,
        inertia: true
    });
    const perfHandle = attachPerf(map);

    const checkpoints = L.layerGroup().addTo(map);
    const connections = L.layerGroup().addTo(map);
    const locateLayer = L.layerGroup().addTo(map);

    let imageHeight = null;
    let imageWidth = null;
    let overlay = null;
    let planUrl = '';

    function pixelToLatLng(px, py) {
        const x = Number(px);
        const y = Number(py);
        if (imageHeight) return L.latLng(imageHeight - y, x);
        return L.latLng(-y, x);
    }

    function latLngToPixel(latlng) {
        const py = imageHeight ? imageHeight - latlng.lat : -latlng.lat;
        return { pos_x_px: latlng.lng, pos_y_px: py };
    }

    function clearPlan() {
        if (overlay) {
            map.removeLayer(overlay);
            overlay = null;
        }
        imageHeight = null;
        imageWidth = null;
        planUrl = '';
    }

    async function setPlan(url) {
        if (url && overlay && planUrl === url) {
            return { width: imageWidth, height: imageHeight };
        }
        clearPlan();
        if (!url) return null;
        const size = await loadImageSize(url);
        imageWidth = size.width;
        imageHeight = size.height;
        const bounds = L.latLngBounds([0, 0], [imageHeight, imageWidth]);
        overlay = L.imageOverlay(url, bounds).addTo(map);
        overlay.bringToBack();
        planUrl = url;
        setPlanVisible(api.layers.plan !== false);
        return { width: imageWidth, height: imageHeight };
    }

    function setPlanVisible(on) {
        if (!overlay || typeof overlay.setOpacity !== 'function') return;
        overlay.setOpacity(on ? 1 : 0);
    }

    function fitToContent(pixels) {
        const pts = (pixels || []).filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
        if (imageWidth && imageHeight) {
            map.fitBounds(L.latLngBounds([0, 0], [imageHeight, imageWidth]));
            return;
        }
        if (pts.length === 0) {
            map.setView(pixelToLatLng(0, 0), 0);
            return;
        }
        const bounds = L.latLngBounds(pts.map((p) => pixelToLatLng(p.x, p.y)));
        map.fitBounds(bounds.pad(0.4));
    }

    const api = {
        map,
        renderer,
        checkpoints,
        connections,
        locateLayer,
        layers: readLayerVisibility(),
        labelFocus: { origin: '', destination: '' },
        refreshStyle() {},
        syncLabels() {},
        onLayers(_next = undefined) {},
        pixelToLatLng,
        latLngToPixel,
        setPlan,
        setPlanVisible,
        clearPlan,
        fitToContent,
        applyZoomStyle() {},
        destroy() {},
        _dead: false
    };

    const cleanups = [];
    let frame = 0;
    let zoomDirty = false;

    function scheduleFrame(fromZoom) {
        if (fromZoom) zoomDirty = true;
        if (frame) return;
        const raf = typeof requestAnimationFrame === 'function'
            ? requestAnimationFrame
            : (fn) => fn();
        frame = raf(() => {
            frame = 0;
            if (api._dead) return;
            const zoomed = zoomDirty;
            zoomDirty = false;
            if (zoomed && typeof api.applyZoomStyle === 'function') api.applyZoomStyle();
            else if (typeof api.syncLabels === 'function') api.syncLabels();
        });
    }

    const controls = mountLayerControls(element, (next) => {
        api.layers = next;
        setPlanVisible(next.plan !== false);
        api.refreshStyle();
        api.onLayers(next);
    });
    map.on('zoomend', () => scheduleFrame(true));
    map.on('moveend', () => scheduleFrame(false));

    if (typeof window !== 'undefined') {
        const onTheme = () => {
            if (!api._dead && typeof api.refreshStyle === 'function') api.refreshStyle();
        };
        window.addEventListener('pov-theme', onTheme);
        cleanups.push(() => window.removeEventListener('pov-theme', onTheme));

        let sizeFrame = 0;
        const onResize = () => {
            if (sizeFrame || api._dead) return;
            const raf = typeof requestAnimationFrame === 'function'
                ? requestAnimationFrame
                : (fn) => fn();
            sizeFrame = raf(() => {
                sizeFrame = 0;
                if (!api._dead && typeof map.invalidateSize === 'function') map.invalidateSize();
            });
        };
        window.addEventListener('resize', onResize);
        window.addEventListener('orientationchange', onResize);
        cleanups.push(() => {
            window.removeEventListener('resize', onResize);
            window.removeEventListener('orientationchange', onResize);
            if (sizeFrame && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(sizeFrame);
        });
    }

    api.destroy = () => {
        if (api._dead) return;
        api._dead = true;
        if (frame && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(frame);
        frame = 0;
        cleanups.forEach((fn) => {
            try { fn(); } catch (_) { /* o mapa já saiu do documento */ }
        });
        cleanups.length = 0;
        if (perfHandle && typeof perfHandle.stop === 'function') perfHandle.stop();
        const container = typeof map.getContainer === 'function' ? map.getContainer() : element;
        const drag = container && container._povNodeDrag;
        if (drag && typeof drag.destroy === 'function') drag.destroy();
        if (controls && typeof controls.destroy === 'function') controls.destroy();
        clearPlan();
        if (typeof map.off === 'function') map.off();
        try {
            if (typeof map.remove === 'function') map.remove();
        } catch (_) { /* já removido */ }
        if (element && element._povFloor === api) delete element._povFloor;
    };
    if (element) element._povFloor = api;
    return api;
}

/**
 * Caminho relativo servido na raiz do frontend (GitHub Pages / pasta frontend).
 * Páginas em /admin/ não podem resolver assets/ a partir da própria URL.
 */
export function resolvePlanImage(planImage, pageHref = undefined) {
    if (!planImage) return '';
    const value = String(planImage).trim();
    if (!value) return '';
    if (/^https?:\/\//i.test(value)) return value;
    const href = pageHref || (typeof window === 'undefined' ? '' : window.location.href);
    if (!href) return value;
    return new URL(value, planImageBase(href)).href;
}

export function planImageBase(pageHref) {
    const url = new URL(pageHref);
    url.hash = '';
    url.search = '';
    const parts = url.pathname.split('/').filter(Boolean);
    if (parts.length && parts[parts.length - 1].includes('.')) parts.pop();
    if (parts.length && parts[parts.length - 1] === 'admin') parts.pop();
    url.pathname = `/${parts.join('/')}${parts.length ? '/' : ''}`;
    if (!url.pathname.endsWith('/')) url.pathname += '/';
    return url.href;
}

function loadImageSize(url): Promise<{ width: number; height: number }> {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve({
            width: img.naturalWidth,
            height: img.naturalHeight
        });
        img.onerror = () => reject(new Error('Não foi possível carregar a planta.'));
        img.src = url;
    });
}
