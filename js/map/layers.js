/**
 * Camadas do mapa: checkpoints, polilinhas e blue dot.
 * No modo somente leitura não há arraste nem handler que grave dados.
 */

import { mapLineColors } from '../core/colors.js';
import { escapeHtml } from '../core/dom.js';

function recordedStyle() {
    return { color: mapLineColors().recorded, weight: 4, opacity: 0.95 };
}

function manualStyle() {
    return { color: mapLineColors().manual, weight: 3, opacity: 0.9, dashArray: '7 8' };
}

export function renderFloorLayers(floor, model, { editable = false, onMove } = {}) {
    floor.connections.clearLayers();
    floor.checkpoints.clearLayers();

    model.polylines.forEach((poly) => {
        const latlngs = poly.points.map((p) => floor.pixelToLatLng(p.x, p.y));
        const style = poly.recorded ? recordedStyle() : manualStyle();
        const line = L.polyline(latlngs, { ...style, interactive: true });
        line.bindPopup(connectionPopup(poly.connection));
        line.addTo(floor.connections);
    });

    model.checkpoints.forEach((cp) => {
        if (!cp.anchor) return;
        const marker = L.marker(floor.pixelToLatLng(cp.anchor.pos_x_px, cp.anchor.pos_y_px), {
            draggable: editable,
            icon: checkpointIcon(),
            title: cp.name,
            keyboard: editable
        });
        marker.bindTooltip(cp.name, {
            permanent: true,
            direction: 'top',
            className: 'cp-label',
            offset: [0, -8]
        });
        if (!editable) {
            marker.bindPopup(`<strong>${escapeHtml(cp.name)}</strong>`);
        }
        if (editable && typeof onMove === 'function') {
            marker.on('dragend', () => {
                onMove(cp.name, floor.latLngToPixel(marker.getLatLng()));
            });
        }
        marker.addTo(floor.checkpoints);
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

function checkpointIcon() {
    return L.divIcon({
        className: 'cp-icon',
        html: '<span class="cp-dot"></span>',
        iconSize: [16, 16],
        iconAnchor: [8, 8]
    });
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
