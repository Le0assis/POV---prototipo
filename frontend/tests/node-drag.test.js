import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'vitest';

import { enableNodeDrag } from '../src/map/layers.ts';
import { viewerNote } from '../src/pages/viewer.ts';

function fakeContainer() {
    const listeners = {};
    return {
        captured: null,
        listeners,
        addEventListener(type, fn) {
            (listeners[type] || (listeners[type] = [])).push(fn);
        },
        setPointerCapture(id) {
            this.captured = id;
        },
        hasPointerCapture(id) {
            return this.captured === id;
        },
        releasePointerCapture() {
            this.captured = null;
        },
        fire(type, event) {
            (listeners[type] || []).forEach((fn) => fn(event));
        }
    };
}

function pointer(type, extra) {
    return {
        pointerId: 1,
        pointerType: type,
        button: 0,
        clientX: 0,
        clientY: 0,
        target: null,
        preventDefault() { this.defaulted = true; },
        stopPropagation() { this.stopped = true; },
        ...extra
    };
}

function harness() {
    const container = fakeContainer();
    const pan = [];
    const map = {
        dragging: {
            disable() { pan.push('off'); },
            enable() { pan.push('on'); }
        },
        getContainer() { return container; },
        mouseEventToContainerPoint(event) { return { x: event.clientX, y: event.clientY }; },
        latLngToContainerPoint(latlng) { return { x: latlng.lng, y: -latlng.lat }; },
        mouseEventToLatLng(event) { return { lat: -event.clientY, lng: event.clientX }; }
    };
    const marker = {
        options: { radius: 7, weight: 2 },
        latlng: { lat: 0, lng: 10 },
        getLatLng() { return this.latlng; },
        setLatLng(latlng) { this.latlng = { lat: latlng.lat, lng: latlng.lng }; return this; }
    };
    const floor = {
        map,
        latLngToPixel(latlng) {
            return { pos_x_px: latlng.lng, pos_y_px: -latlng.lat };
        }
    };
    return { container, pan, map, marker, floor };
}

async function drop(container, type, at) {
    container.fire('pointerdown', pointer(type, { clientX: 10, clientY: 0 }));
    container.fire('pointermove', pointer(type, { clientX: at, clientY: 4 }));
    container.fire('pointerup', pointer(type, { clientX: at, clientY: 4 }));
    await Promise.resolve();
    await Promise.resolve();
}

test('arrastar com mouse ou toque solta o pan, captura o ponteiro e grava no drop', async () => {
    const mouse = harness();
    const saved = [];
    const mouseHost = enableNodeDrag(mouse.marker, mouse.floor, 'Sala', (name, pixel) => {
        saved.push({ name, pixel, kind: 'mouse' });
        return true;
    });
    mouse.container.fire('pointerdown', pointer('mouse', { clientX: 80, clientY: 80 }));
    assert.deepEqual(mouse.pan, []);
    assert.equal(mouse.container.captured, null);

    mouse.container.fire('pointerdown', pointer('mouse', { clientX: 10, clientY: 0 }));
    assert.deepEqual(mouse.pan, ['off']);
    assert.equal(mouse.container.captured, 1);
    assert.equal(mouse.marker._povDragging, true);
    mouse.container.fire('pointermove', pointer('mouse', { clientX: 40, clientY: 6 }));
    assert.equal(mouse.marker.getLatLng().lng, 40);
    mouse.container.fire('pointerup', pointer('mouse', { clientX: 40, clientY: 6 }));
    await mouseHost.settled;
    assert.deepEqual(mouse.pan, ['off', 'on']);
    assert.equal(saved.length, 1);
    assert.equal(saved[0].name, 'Sala');
    assert.equal(saved[0].pixel.pos_x_px, 40);
    assert.equal(saved[0].pixel.pos_y_px, 6);
    assert.equal(mouse.marker._povDragging, false);

    const touch = harness();
    const touched = [];
    const touchHost = enableNodeDrag(touch.marker, touch.floor, 'Hall', (name, pixel) => {
        touched.push({ name, pixel });
        return true;
    });
    await drop(touch.container, 'touch', 22);
    await touchHost.settled;
    assert.deepEqual(touch.pan, ['off', 'on']);
    assert.equal(touch.container.captured, null);
    assert.equal(touched.length, 1);
    assert.equal(touched[0].name, 'Hall');
    assert.equal(touched[0].pixel.pos_x_px, 22);
    assert.equal(touched[0].pixel.pos_y_px, 4);
    assert.equal(touch.marker.getLatLng().lng, 22);
});

test('falha no PATCH devolve o nó sem recarregar; cancelar não grava', async () => {
    const fail = harness();
    let calls = 0;
    const host = enableNodeDrag(fail.marker, fail.floor, 'Sala', () => {
        calls += 1;
        return false;
    });
    await drop(fail.container, 'mouse', 55);
    await host.settled;
    assert.equal(calls, 1);
    assert.equal(fail.marker.getLatLng().lng, 10);
    assert.equal(fail.marker.getLatLng().lat, 0);
    assert.deepEqual(fail.pan, ['off', 'on']);

    const cancel = harness();
    let patches = 0;
    enableNodeDrag(cancel.marker, cancel.floor, 'Sala', () => {
        patches += 1;
        return true;
    });
    cancel.container.fire('pointerdown', pointer('touch', { clientX: 10, clientY: 0 }));
    cancel.container.fire('pointermove', pointer('touch', { clientX: 30, clientY: 2 }));
    cancel.container.fire('pointercancel', pointer('touch', { clientX: 30, clientY: 2 }));
    assert.equal(patches, 0);
    assert.equal(cancel.marker.getLatLng().lng, 10);
    assert.deepEqual(cancel.pan, ['off', 'on']);
});

test('a legenda fica fora do zoom e a atribuição pode quebrar linha', () => {
    const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
    const mapCss = readFileSync(path.join(root, 'css/map.css'), 'utf8');
    const layers = mapCss.slice(mapCss.indexOf('.map-layers {'), mapCss.indexOf('.map-layers-toggle'));
    assert.match(layers, /right:\s*8px/);
    assert.match(layers, /min-width:\s*0/);
    assert.match(layers, /max-width:\s*calc\(100% - 76px\)/);
    assert.doesNotMatch(layers, /left:\s*8px/);
    assert.match(mapCss, /\.map-layers:not\(\.is-open\) \.map-layers-options \{\s*display:\s*none/);
    assert.match(mapCss, /\.map-stage \.leaflet-bottom\.leaflet-right \{[^}]*left:\s*8px/);
    assert.match(mapCss, /\.map-stage \.leaflet-control-attribution \{[^}]*min-width:\s*0/);
    assert.match(mapCss, /\.map-stage\.leaflet-container[\s\S]*background-color:\s*var\(--bg\)/);
});

test('o viewer lista a aresta manual', () => {
    const note = viewerNote({
        missingAnchor: [{}],
        polylines: [
            { recorded: false, source: 'Recepção', target: 'Sala' },
            { recorded: true, source: 'Sala', target: 'Copa' }
        ]
    });
    assert.match(note, /1 conexão/);
    assert.match(note, /Arestas manuais: Recepção → Sala/);
    assert.doesNotMatch(note, /Copa/);
});
