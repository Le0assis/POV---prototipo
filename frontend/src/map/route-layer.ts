/**
 * Polilinha da prévia: traço grosso na cor primária, contorno branco,
 * marcador "você" na origem e marcador no destino.
 * O enquadramento reserva a barra de cima e a busca de baixo quando elas
 * cobrem o mapa, e também o painel de passos.
 */

import { escapeHtml } from '../core/dom.js';
import { tokenColor } from '../core/colors.js';
import { pointsUntil, routeSignature } from './simplify.js';
import { routeWeight } from './style.js';

const PRIMARY_FALLBACK = '#2563EB';
const OUTLINE_FALLBACK = '#FFFFFF';

export function fitPadding({ top = 0, bottom = 0, inset = 24 } = {} as any) {
    const topPad = Math.max(0, Number(top) || 0);
    const bottomPad = Math.max(0, Number(bottom) || 0);
    const gutter = Number.isFinite(Number(inset)) ? Number(inset) : 24;
    return {
        paddingTopLeft: [gutter, gutter + topPad],
        paddingBottomRight: [gutter, gutter + bottomPad]
    };
}

/** Sobreposição real da barra, da busca e do painel com o retângulo do mapa. */
export function chromePadding(mapRect, { topRect = null, bottomRect = null, flowRect = null, inset = 24 } = {} as any) {
    const top = overlap(mapRect, topRect, 'top');
    const search = overlap(mapRect, bottomRect, 'bottom');
    const panel = overlap(mapRect, flowRect, 'bottom');
    return fitPadding({ top, bottom: Math.max(search, panel), inset });
}

export function createRouteLayer(floor) {
    const group = L.layerGroup().addTo(floor.map);
    let points = [];
    let signature = '';
    let walkedLine = null;
    let outlineLine = null;
    let mainLine = null;
    let visible = !floor.layers || floor.layers.route !== false;

    function clear() {
        group.clearLayers();
        points = [];
        signature = '';
        walkedLine = null;
        outlineLine = null;
        mainLine = null;
    }

    function applyWeight() {
        const zoom = floor.map && typeof floor.map.getZoom === 'function' ? floor.map.getZoom() : 0;
        const weight = routeWeight(zoom);
        if (outlineLine) outlineLine.setStyle({ weight: weight + 6, color: cssColor('--surface', OUTLINE_FALLBACK) });
        if (mainLine) mainLine.setStyle({ weight, color: cssColor('--primary', PRIMARY_FALLBACK) });
        if (walkedLine) walkedLine.setStyle({ weight, color: tokenColor('walked') });
    }

    function setVisible(on) {
        visible = on !== false;
        if (!floor.map) return;
        const onMap = typeof floor.map.hasLayer === 'function' && floor.map.hasLayer(group);
        if (visible && !onMap) group.addTo(floor.map);
        if (!visible && onMap) floor.map.removeLayer(group);
    }

    function show(route, { markOrigin = true } = {} as any) {
        const next = routeSignature(route);
        if (next && next === signature) return;
        clear();
        signature = next;
        if (!route) return;
        points = Array.isArray(route.points) ? route.points.filter(finitePoint) : [];
        if (points.length >= 2) {
            const latlngs = points.map((point) => floor.pixelToLatLng(point.x, point.y));
            const weight = routeWeight(floor.map && floor.map.getZoom ? floor.map.getZoom() : 0);
            outlineLine = L.polyline(latlngs, {
                color: cssColor('--surface', OUTLINE_FALLBACK),
                weight: weight + 6,
                opacity: 1,
                lineCap: 'round',
                lineJoin: 'round',
                interactive: false,
                smoothFactor: 1.5,
                renderer: floor.renderer,
                className: 'route-line-outline'
            }).addTo(group);
            mainLine = L.polyline(latlngs, {
                color: cssColor('--primary', PRIMARY_FALLBACK),
                weight,
                opacity: 1,
                lineCap: 'round',
                lineJoin: 'round',
                interactive: false,
                smoothFactor: 1.5,
                renderer: floor.renderer,
                className: 'route-line'
            }).addTo(group);
        }

        const stops = Array.isArray(route.checkpoints) ? route.checkpoints : [];
        const origin = stops[0];
        const destination = stops.length > 1 ? stops[stops.length - 1] : null;
        if (origin && markOrigin) addOrigin(floor, group, origin);
        if (destination) addDestination(floor, group, destination);
        bringGroupToFront(group);
        setVisible(floor.layers ? floor.layers.route !== false : visible);
    }

    function setProgress(fraction) {
        if (points.length < 2) return;
        const walked = pointsUntil(points, fraction);
        const latlngs = walked.map((point) => floor.pixelToLatLng(point.x, point.y));
        if (!walkedLine) {
            walkedLine = L.polyline(latlngs, {
                color: tokenColor('walked'),
                weight: routeWeight(floor.map && floor.map.getZoom ? floor.map.getZoom() : 0),
                opacity: 1,
                lineCap: 'round',
                lineJoin: 'round',
                interactive: false,
                renderer: floor.renderer
            }).addTo(group);
            return;
        }
        walkedLine.setLatLngs(latlngs);
    }

    function fit(padding) {
        if (!points.length || !floor.map) return;
        const latlngs = points.map((point) => floor.pixelToLatLng(point.x, point.y));
        if (latlngs.length === 1) {
            floor.map.setView(latlngs[0], 0, { animate: false });
            return;
        }
        const options = {
            paddingTopLeft: (padding && padding.paddingTopLeft) || [24, 24],
            paddingBottomRight: (padding && padding.paddingBottomRight) || [24, 24],
            animate: false
        };
        floor.map.fitBounds(L.latLngBounds(latlngs), options);
    }

    if (floor.map && typeof floor.map.on === 'function') floor.map.on('zoomend', applyWeight);
    if (typeof window !== 'undefined') window.addEventListener('pov-theme', applyWeight);
    setVisible(visible);
    return { show, clear, fit, setProgress, setVisible };
}

function addOrigin(floor, group, checkpoint) {
    if (!Number.isFinite(checkpoint.pos_x_px) || !Number.isFinite(checkpoint.pos_y_px)) return;
    const marker = L.marker(floor.pixelToLatLng(checkpoint.pos_x_px, checkpoint.pos_y_px), {
        icon: L.divIcon({
            className: 'blue-dot-icon you-marker route-origin',
            html: '<div class="blue-dot"><span class="blue-dot-arrow"></span><span class="blue-dot-core"></span></div>',
            iconSize: [28, 28],
            iconAnchor: [14, 14]
        }),
        interactive: false,
        keyboard: false,
        zIndexOffset: 1000,
        title: 'você'
    });
    marker.bindTooltip('você', {
        permanent: true,
        direction: 'right',
        className: 'you-label',
        offset: [16, 0]
    });
    marker.addTo(group);
}

function addDestination(floor, group, checkpoint) {
    if (!Number.isFinite(checkpoint.pos_x_px) || !Number.isFinite(checkpoint.pos_y_px)) return;
    const name = checkpoint.name || checkpoint.label || checkpoint.slug || 'Destino';
    const marker = L.marker(floor.pixelToLatLng(checkpoint.pos_x_px, checkpoint.pos_y_px), {
        icon: L.divIcon({
            className: 'route-destination-icon',
            html: '<span class="route-dest-dot"></span>',
            iconSize: [22, 22],
            iconAnchor: [11, 11]
        }),
        interactive: false,
        keyboard: false,
        zIndexOffset: 900,
        title: name
    });
    marker.bindTooltip(escapeHtml(name), {
        permanent: true,
        direction: 'top',
        className: 'route-dest-label',
        offset: [0, -12]
    });
    marker.addTo(group);
}

/** LayerGroup nesta build do Leaflet não tem bringToFront; os filhos (linha e marcador) têm. */
function bringGroupToFront(layer) {
    if (!layer) return;
    if (typeof layer.bringToFront === 'function') {
        layer.bringToFront();
        return;
    }
    if (typeof layer.eachLayer === 'function') {
        layer.eachLayer((child) => bringGroupToFront(child));
    }
}

function finitePoint(point) {
    return Boolean(point) && Number.isFinite(point.x) && Number.isFinite(point.y);
}

function overlap(mapRect, barRect, edge) {
    if (!mapRect || !barRect) return 0;
    if (edge === 'top') return Math.max(0, barRect.bottom - mapRect.top);
    return Math.max(0, mapRect.bottom - barRect.top);
}

function cssColor(name, fallback) {
    if (typeof document === 'undefined' || typeof getComputedStyle !== 'function') return fallback;
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
}
