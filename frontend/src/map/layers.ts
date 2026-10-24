/**
 * Camadas do mapa: checkpoints em circleMarker e polilinhas no canvas.
 * Atualiza pelo id. O popup nasce no clique.
 */

import { mapLineColors, tokenColor } from '../core/colors.js';
import { escapeHtml } from '../core/dom.js';
import { pixelTolerance, simplifyPath } from './simplify.js';
import { chooseLabels, defaultLayerVisibility, lineWeight } from './style.js';

function recordedStyle(zoom) {
    return { color: mapLineColors().recorded, weight: lineWeight(zoom, true), opacity: 0.95 };
}

function manualStyle(zoom) {
    return { color: mapLineColors().manual, weight: lineWeight(zoom, false), opacity: 0.9, dashArray: '7 8' };
}

export function checkpointStyle(active) {
    const color = tokenColor(active ? 'destination' : 'checkpoint');
    return {
        radius: active ? 12 : 7,
        weight: active ? 4 : 2,
        color,
        fillColor: color,
        fillOpacity: 1
    };
}

export function renderFloorLayers(floor, model, { editable = false, onMove, showManual = false } = {} as any) {
    const index = floor.layerIndex || (floor.layerIndex = { lines: new Map(), points: new Map() });
    floor.layers = floor.layers || defaultLayerVisibility();
    floor._styleModel = model;
    floor._styleOptions = { editable, onMove, showManual };
    floor.refreshStyle = () => {
        if (floor._styleModel) renderFloorLayers(floor, floor._styleModel, floor._styleOptions || {});
    };
    floor.syncLabels = () => syncLabels(floor);
    floor.applyZoomStyle = () => applyLineWeights(floor);
    syncLines(floor, index, model);
    syncPoints(floor, index, model, { editable, onMove });
    syncLabels(floor);
}

function syncLines(floor, index, model) {
    const seen = new Set();
    const showManual = Boolean(floor._styleOptions && floor._styleOptions.showManual);
    const tolerance = pixelTolerance(model.config && model.config.px_per_m);
    (model.polylines || []).forEach((poly, order) => {
        const key = poly.id != null ? `id:${poly.id}` : `pair:${poly.source}->${poly.target}:${order}`;
        seen.add(key);
        const geom = geometryKey(poly.points, tolerance);
        const zoom = floor.map && typeof floor.map.getZoom === 'function' ? floor.map.getZoom() : 0;
        const layers = floor.layers || defaultLayerVisibility();
        const shown = poly.recorded ? layers.recorded !== false : layers.manual !== false;
        const style = { ...(poly.recorded ? recordedStyle(zoom) : manualStyle(zoom)), smoothFactor: 1.5 };
        let line = index.lines.get(key);
        if (!line) {
            const latlngs = simplifiedLatLngs(floor, poly.points, tolerance);
            line = L.polyline(latlngs, {
                ...style,
                interactive: true,
                renderer: floor.renderer
            });
            line.on('click', () => {
                line.bindPopup(connectionPopup(line.connection)).openPopup();
            });
            line._povGeomKey = geom;
            index.lines.set(key, line);
        } else {
            if (line._povGeomKey !== geom) {
                line.setLatLngs(simplifiedLatLngs(floor, poly.points, tolerance));
                line._povGeomKey = geom;
            }
            line.setStyle(style);
        }
        line._povRecorded = Boolean(poly.recorded);
        line.connection = poly.connection;
        syncManualLabel(line, poly, showManual);
        if (shown) {
            if (!floor.connections.hasLayer(line)) line.addTo(floor.connections);
        } else if (floor.connections.hasLayer(line)) {
            floor.connections.removeLayer(line);
        }
    });
    index.lines.forEach((line, key) => {
        if (seen.has(key)) return;
        if (typeof line.off === 'function') line.off();
        floor.connections.removeLayer(line);
        index.lines.delete(key);
    });
}

function simplifiedLatLngs(floor, points, tolerance) {
    return simplifyPath(points, tolerance).map((point) => floor.pixelToLatLng(point.x, point.y));
}

function geometryKey(points, tolerance) {
    const list = Array.isArray(points) ? points : [];
    let acc = list.length;
    const step = Math.max(1, Math.floor(list.length / 8));
    for (let i = 0; i < list.length; i += step) {
        const point = list[i] || {};
        acc = (Math.imul(acc, 33) + Math.round(Number(point.x) || 0) + Math.imul(Math.round(Number(point.y) || 0), 131)) | 0;
    }
    const last = list.length ? list[list.length - 1] : null;
    if (last) acc = (Math.imul(acc, 33) + Math.round(Number(last.x) || 0) + Math.imul(Math.round(Number(last.y) || 0), 17)) | 0;
    return `${tolerance}:${list.length}:${acc}`;
}

function applyLineWeights(floor) {
    const index = floor.layerIndex;
    if (!index) return;
    const zoom = floor.map && typeof floor.map.getZoom === 'function' ? floor.map.getZoom() : 0;
    index.lines.forEach((line) => {
        const style = line._povRecorded ? recordedStyle(zoom) : manualStyle(zoom);
        if (typeof line.setStyle === 'function') line.setStyle({ ...style, smoothFactor: 1.5 });
    });
    syncLabels(floor);
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
        marker.checkpointName = cp.name;
    });
    index.points.forEach((marker, key) => {
        if (seen.has(key)) return;
        if (typeof marker._povDragOff === 'function') marker._povDragOff();
        floor.checkpoints.removeLayer(marker);
        index.points.delete(key);
    });
}

function mapHasView(map) {
    try {
        if (!map || typeof map.getCenter !== 'function') return false;
        map.getCenter();
        return true;
    } catch (_) {
        return false;
    }
}

function syncLabels(floor) {
    const index = floor.layerIndex;
    if (!index || !mapHasView(floor.map) || typeof floor.map.latLngToContainerPoint !== 'function') return;
    const layers = floor.layers || defaultLayerVisibility();
    const focus = floor.labelFocus || {};
    const zoom = typeof floor.map.getZoom === 'function' ? floor.map.getZoom() : 0;
    const items = [];
    index.points.forEach((marker, key) => {
        const name = marker.checkpointName || key;
        const slug = marker.checkpointSlug || '';
        const latlng = typeof marker.getLatLng === 'function' ? marker.getLatLng() : null;
        if (!latlng) return;
        const point = floor.map.latLngToContainerPoint(latlng);
        const pinned = samePoint(focus.origin, slug, name) || samePoint(focus.destination, slug, name);
        items.push({
            id: key,
            name,
            pinned,
            x: point.x - 24,
            y: point.y - 28,
            marker
        });
    });
    const visible = new Set(chooseLabels(items, { labelsOn: layers.labels !== false, zoom }));
    items.forEach((item) => setPermanentLabel(item.marker, visible.has(item.id), item.name));
}

function samePoint(wanted, slug, name) {
    if (!wanted) return false;
    const value = String(wanted);
    return value === slug || value === name;
}

function setPermanentLabel(marker, show, name) {
    const tip = typeof marker.getTooltip === 'function' ? marker.getTooltip() : null;
    const permanent = Boolean(tip && tip.options && tip.options.permanent);
    if (tip && permanent === show) return;
    if (tip && typeof marker.unbindTooltip === 'function') marker.unbindTooltip();
    marker.bindTooltip(name, {
        permanent: show,
        direction: 'top',
        className: 'cp-label',
        offset: [0, -8]
    });
}

function enableDrag(marker, floor, name, onMove) {
    enableNodeDrag(marker, floor, name, onMove);
}

/**
 * Arrasta o nó com pointer events (mouse e toque). A captura fica no
 * container, o pan do mapa sai enquanto o ponteiro está preso, e o PATCH
 * sai no pointerup. Falha ou cancelamento devolve o nó ao lugar, sem recarregar.
 */
export function enableNodeDrag(marker, floor, name, onMove) {
    const map = floor && floor.map;
    const container = map && typeof map.getContainer === 'function' ? map.getContainer() : null;
    if (!container || !marker || typeof onMove !== 'function') return null;
    const host = dragHost(container, map);
    host.track(marker, floor, name, onMove);
    return host;
}

function dragHost(container, map) {
    if (container._povNodeDrag) return container._povNodeDrag;
    const markers = new Map();
    let active = null;
    const host = {
        markers,
        settled: Promise.resolve(),
        track(marker, floor, name, onMove) {
            markers.set(marker, { floor, name, onMove });
            marker._povDragOff = () => markers.delete(marker);
        },
        destroy() {}
    };

    function pointOf(event) {
        if (typeof map.mouseEventToContainerPoint === 'function') return map.mouseEventToContainerPoint(event);
        return { x: event.clientX, y: event.clientY };
    }

    function hitRadius(marker, event) {
        const base = Number(marker.options && marker.options.radius) || 7;
        const weight = Number(marker.options && marker.options.weight) || 0;
        const coarse = event.pointerType === 'touch' || event.pointerType === 'pen';
        return base + weight + (coarse ? 28 : 8);
    }

    function hit(event) {
        if (typeof map.latLngToContainerPoint !== 'function') return null;
        const point = pointOf(event);
        let found = null;
        let best = Infinity;
        markers.forEach((meta, marker) => {
            if (typeof marker.getLatLng !== 'function') return;
            const center = map.latLngToContainerPoint(marker.getLatLng());
            const dist = Math.hypot(point.x - center.x, point.y - center.y);
            if (dist <= hitRadius(marker, event) && dist < best) {
                best = dist;
                found = { marker, meta };
            }
        });
        return found;
    }

    function setPan(on) {
        const dragging = map.dragging;
        if (!dragging) return;
        const fn = on ? dragging.enable : dragging.disable;
        if (typeof fn === 'function') fn.call(dragging);
    }

    function onControl(event) {
        const target = event.target;
        return Boolean(target && typeof target.closest === 'function'
            && target.closest('.map-layers, .leaflet-control'));
    }

    function onDown(event) {
        if (active || onControl(event)) return;
        if (event.pointerType === 'mouse' && event.button !== 0) return;
        const found = hit(event);
        if (!found) return;
        if (typeof event.preventDefault === 'function') event.preventDefault();
        if (typeof event.stopPropagation === 'function') event.stopPropagation();
        const marker = found.marker;
        const start = marker.getLatLng();
        marker._povDragging = true;
        setPan(false);
        if (typeof container.setPointerCapture === 'function') {
            try { container.setPointerCapture(event.pointerId); } catch (_) { /* ponteiro já encerrado */ }
        }
        active = {
            pointerId: event.pointerId,
            marker,
            meta: found.meta,
            origin: start ? { lat: start.lat, lng: start.lng } : null
        };
    }

    function onMove(event) {
        if (!active || event.pointerId !== active.pointerId) return;
        if (typeof event.preventDefault === 'function') event.preventDefault();
        if (typeof event.stopPropagation === 'function') event.stopPropagation();
        if (typeof map.mouseEventToLatLng !== 'function') return;
        active.marker.setLatLng(map.mouseEventToLatLng(event));
    }

    function release(event) {
        if (!event || typeof container.releasePointerCapture !== 'function') return;
        try {
            if (typeof container.hasPointerCapture !== 'function' || container.hasPointerCapture(event.pointerId)) {
                container.releasePointerCapture(event.pointerId);
            }
        } catch (_) { /* captura já solta */ }
    }

    function restore(marker, origin) {
        if (origin && typeof marker.setLatLng === 'function') marker.setLatLng(origin);
    }

    function finish(event, cancel) {
        if (!active || !event || event.pointerId !== active.pointerId) return;
        const drag = active;
        active = null;
        setPan(true);
        release(event);
        if (cancel) {
            drag.marker._povDragging = false;
            restore(drag.marker, drag.origin);
            return;
        }
        const latlng = typeof drag.marker.getLatLng === 'function' ? drag.marker.getLatLng() : null;
        const pixel = drag.meta.floor.latLngToPixel(latlng);
        host.settled = Promise.resolve()
            .then(() => drag.meta.onMove(drag.meta.name, pixel))
            .then((ok) => {
                if (ok === false) restore(drag.marker, drag.origin);
            })
            .catch(() => {
                restore(drag.marker, drag.origin);
            })
            .finally(() => {
                drag.marker._povDragging = false;
            });
    }

    function onUp(event) { finish(event, false); }
    function onCancel(event) { finish(event, true); }

    container.addEventListener('pointerdown', onDown, true);
    container.addEventListener('pointermove', onMove, true);
    container.addEventListener('pointerup', onUp, true);
    container.addEventListener('pointercancel', onCancel, true);
    host.destroy = () => {
        container.removeEventListener('pointerdown', onDown, true);
        container.removeEventListener('pointermove', onMove, true);
        container.removeEventListener('pointerup', onUp, true);
        container.removeEventListener('pointercancel', onCancel, true);
        markers.clear();
        active = null;
        if (container._povNodeDrag === host) delete container._povNodeDrag;
    };
    container._povNodeDrag = host;
    return host;
}

function syncManualLabel(line, poly, showManual) {
    const manual = Boolean(showManual) && !poly.recorded;
    const text = manual ? `Manual: ${poly.source} → ${poly.target}` : '';
    const tip = typeof line.getTooltip === 'function' ? line.getTooltip() : null;
    const manualTip = Boolean(tip && tip.options && String(tip.options.className || '').includes('edge-manual'));
    if (!manual) {
        if (manualTip && typeof line.unbindTooltip === 'function') line.unbindTooltip();
        return;
    }
    if (!tip && typeof line.bindTooltip === 'function') {
        line.bindTooltip(text, { sticky: true, className: 'cp-label edge-manual', opacity: 1 });
        return;
    }
    if (manualTip && typeof tip.setContent === 'function') tip.setContent(text);
}

export function createBlueDot(floor, { label = '', cone = false, zIndex = 800 } = {} as any) {
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
