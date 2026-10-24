/** Visibilidade das camadas, espessura por zoom e quais rótulos cabem na tela. */

export const LAYER_STORAGE_KEY = 'pov.map.layers';
export const LABEL_MIN_ZOOM = 1;

export function defaultLayerVisibility() {
    return { plan: true, recorded: true, manual: true, labels: true, route: true };
}

export function readLayerVisibility(storage = undefined) {
    const base = defaultLayerVisibility();
    const bag = storage === undefined ? defaultStorage() : storage;
    if (!bag) return base;
    try {
        const raw = bag.getItem(LAYER_STORAGE_KEY);
        if (!raw) return base;
        const data = JSON.parse(raw);
        if (!data || typeof data !== 'object') return base;
        Object.keys(base).forEach((key) => {
            if (typeof data[key] === 'boolean') base[key] = data[key];
        });
        return base;
    } catch (_) {
        return base;
    }
}

export function saveLayerVisibility(prefs, storage = undefined) {
    const next = defaultLayerVisibility();
    const source = prefs || {};
    Object.keys(next).forEach((key) => {
        if (typeof source[key] === 'boolean') next[key] = source[key];
    });
    const bag = storage === undefined ? defaultStorage() : storage;
    if (bag) bag.setItem(LAYER_STORAGE_KEY, JSON.stringify(next));
    return next;
}

/** Gravado um pouco mais grosso que o manual. Zoom 0 mantém 4 e 3. */
export function lineWeight(zoom, recorded) {
    const z = Number.isFinite(Number(zoom)) ? Number(zoom) : 0;
    const base = recorded ? 4 : 3;
    return Math.max(2, Math.min(9, base + z * 0.75));
}

export function routeWeight(zoom) {
    const z = Number.isFinite(Number(zoom)) ? Number(zoom) : 0;
    return Math.max(4, Math.min(12, 8 + z));
}

/**
 * Rótulos visíveis. Origem e destino (pinned) ficam mesmo abaixo do zoom
 * e mesmo quando se sobrepõem. Os outros só entram acima do zoom mínimo
 * e se o retângulo não cruza um rótulo já escolhido.
 */
export function chooseLabels(items, { labelsOn = true, zoom = 0, minZoom = LABEL_MIN_ZOOM } = {} as any) {
    const visible = [];
    const boxes = [];
    const list = Array.isArray(items) ? items : [];
    const ordered = list.filter((item) => item && item.pinned).concat(list.filter((item) => item && !item.pinned));
    ordered.forEach((item) => {
        if (!labelsOn) return;
        if (!item.pinned && Number(zoom) < minZoom) return;
        const box = labelBox(item);
        const hit = boxes.some((other) => overlaps(other, box));
        if (hit && !item.pinned) return;
        boxes.push(box);
        visible.push(item.id);
    });
    return visible;
}

function labelBox(item) {
    const width = Math.max(36, String(item.name || '').length * 7);
    return {
        x: Number(item.x) || 0,
        y: Number(item.y) || 0,
        w: width,
        h: 16
    };
}

function overlaps(a, b) {
    return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

function defaultStorage() {
    try {
        if (typeof localStorage === 'undefined') return null;
        return localStorage;
    } catch (_) {
        return null;
    }
}
