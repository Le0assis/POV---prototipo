/**
 * Camadas do mapa: checkpoints em circleMarker e polilinhas no canvas.
 * Atualiza pelo id. O popup nasce no clique.
 */

import { mapLineColors, tokenColor } from '../core/colors.js';
import { escapeHtml } from '../core/dom.js';
import { pixelTolerance, simplifyPath } from './simplify.js';

function recordedStyle() {
    return { color: mapLineColors().recorded, weight: 4, opacity: 0.95 };
}

function manualStyle() {
    return { color: mapLineColors().manual, weight: 3, opacity: 0.9, dashArray: '7 8' };
}

export function checkpointStyle(active) {
    const color = tokenColor('checkpoint');
    return {
        radius: active ? 10 : 7,
        weight: active ? 3 : 2,
        color,
        fillColor: active ? tokenColor('walked') : color,
        fillOpacity: 1
    };
}

export function renderFloorLayers(floor, model, { editable = false, onMove } = {}) {
    const index = floor.layerIndex || (floor.layerIndex = { lines: new Map(), points: new Map() });
    syncLines(floor, index, model);
    syncPoints(floor, index, model, { editable, onMove });
}

function syncLines(floor, index, model) {
    const seen = new Set();
    const tolerance = pixelTolerance(model.config && model.config.px_per_m);
    (model.polylines || []).forEach((poly, order) => {
        const key = poly.id != null ? `id:${poly.id}` : `pair:${poly.source}->${poly.target}:${order}`;
        seen.add(key);
        const points = simplifyPath(poly.points, tolerance);
        const latlngs = points.map((point) => floor.pixelToLatLng(point.x, point.y));
        const style = { ...(poly.recorded ? recordedStyle() : manualStyle()), smoothFactor: 1.5 };
        let line = index.lines.get(key);
        if (!line) {
            line = L.polyline(latlngs, {
                ...style,
                interactive: true,
                renderer: floor.renderer
            });
            line.on('click', () => {
                line.bindPopup(connectionPopup(line.connection)).openPopup();
            });
            line.addTo(floor.connections);
            index.lines.set(key, line);
        } else {
            line.setLatLngs(latlngs);
            line.setStyle(style);
        }
        line.connection = poly.connection;
    });
    index.lines.forEach((line, key) => {
        if (seen.has(key)) return;
        floor.connections.removeLayer(line);
        index.lines.delete(key);
    });
}

function syncPoints(floor, index, model, { editable, onMove }) {
    const seen = new Set();
    (model.checkpoints || []).forEach((cp) => {
        if (!cp.anchor) return;
        const key = cp.name;
        seen.add(key);
        const latlng = floor.pixelToLatLng(cp.anchor.pos_x_px, cp.anchor.pos_y_px);
        let marker = index.points.get(key);
        if (!marker) {
            marker = L.circleMarker(latlng, {
                ...checkpointStyle(false),
                interactive: true,
                renderer: floor.renderer
            });
            marker.checkpointName = cp.name;
            marker.bindTooltip(cp.name, { direction: 'top', className: 'cp-label', offset: [0, -8] });
            if (!editable) marker.on('click', () => marker.bindPopup(`<strong>${escapeHtml(cp.name)}</strong>`).openPopup());
            if (editable && typeof onMove === 'function') enableDrag(marker, floor, cp.name, onMove);
            marker.addTo(floor.checkpoints);
            index.points.set(key, marker);
        } else if (!marker._povDragging) {
            marker.setLatLng(latlng);
        }
        marker.checkpointSlug = cp.slug || cp.name;
    });
    index.points.forEach((marker, key) => {
        if (seen.has(key)) return;
        floor.checkpoints.removeLayer(marker);
        index.points.delete(key);
    });
}

function enableDrag(marker, floor, name, onMove) {
    marker.on('mousedown', (event) => {
        if (event.originalEvent) L.DomEvent.stop(event.originalEvent);
        marker._povDragging = true;
        floor.map.dragging.disable();
        const move = (ev) => marker.setLatLng(ev.latlng);
        const up = (ev) => {
            marker._povDragging = false;
            floor.map.dragging.enable();
            floor.map.off('mousemove', move);
            floor.map.off('mouseup', up);
            onMove(name, floor.latLngToPixel(marker.getLatLng() || ev.latlng));
        };
        floor.map.on('mousemove', move);
        floor.map.on('mouseup', up);
    });
}

export function createBlueDot(floor, { label = '', cone = false, zIndex = 800 } = {}) {
    const size = cone ? 96 : 28;
    const html = cone
        ? '<div class="blue-dot has-cone"><span class="blue-dot-cone" aria-hidden="true"></span><span class="blue-dot-arrow"></span><span class="blue-dot-core"></span></div>'
        : '<div class="blue-dot"><span class="blue-dot-arrow"></span><span class="blue-dot-core"></span></div>';
    const icon = L.divIcon({
        className: label ? 'blue-dot-icon you-marker' : 'blue-dot-icon',
        html,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2]
    });
    const marker = L.marker(floor.pixelToLatLng(0, 0), {
        icon,
        interactive: false,
        keyboard: false,
        zIndexOffset: zIndex,
        title: label || undefined
    });
    if (label) {
        marker.bindTooltip(label, {
            permanent: true,
            direction: 'right',
            className: 'you-label',
            offset: [cone ? 40 : 16, 0]
        });
    }
    let visible = false;

    function setPixel(x, y) {
        marker.setLatLng(floor.pixelToLatLng(x, y));
        if (!visible) {
            marker.addTo(floor.locateLayer);
            visible = true;
        }
    }

    function setHeading(cssDeg) {
        const el = marker.getElement();
        if (!el) return;
        const dot = el.querySelector('.blue-dot');
        if (dot && Number.isFinite(cssDeg)) dot.style.transform = `rotate(${cssDeg}deg)`;
    }

    function hide() {
        if (visible) floor.locateLayer.removeLayer(marker);
        visible = false;
    }

    return { setPixel, setHeading, hide };
}

export function contentPixels(model) {
    const pts = [];
    model.checkpoints.forEach((cp) => {
        if (cp.anchor) pts.push({ x: cp.anchor.pos_x_px, y: cp.anchor.pos_y_px });
    });
    model.polylines.forEach((poly) => {
        poly.points.forEach((p) => pts.push(p));
    });
    return pts;
}

function connectionPopup(connection) {
    const when = formatWhen(connection && connection.recorded_at);
    const steps = connection && connection.steps_count != null ? connection.steps_count : '—';
    const distance = Number(connection && connection.distance_m);
    const distLabel = Number.isFinite(distance) ? `${distance.toFixed(2)} m` : '—';
    const samples = connection && connection.samples_count != null ? connection.samples_count : '—';
    const trace = connection && connection.active_trace_id != null ? connection.active_trace_id : '—';
    const origin = connection && connection.origin === 'recorded' ? 'gravação' : 'manual';
    return `
        <div class="map-popup">
            <strong>${escapeHtml(connection.source)} → ${escapeHtml(connection.target)}</strong>
            <p>Origem do traço: ${escapeHtml(origin)}</p>
            <p>Passos: ${escapeHtml(steps)} · Distância: ${escapeHtml(distLabel)}</p>
            <p>Amostras: ${escapeHtml(samples)} · Trace: ${escapeHtml(trace)}</p>
            <p>Data: ${escapeHtml(when)}</p>
        </div>
    `;
}

function formatWhen(value) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString('pt-BR');
}
