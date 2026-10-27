/** Caixa de camadas do mapa. O estado fica em localStorage. */

import { compassNeedleDeg } from '../sensors/angles.js';
import { HeadingProvider, compassBearingDeg } from '../sensors/heading.js';
import { readLayerVisibility, saveLayerVisibility } from './style.js';

const FIELDS = [
    ['plan', 'Planta'],
    ['recorded', 'Gravados'],
    ['manual', 'Manuais'],
    ['labels', 'Rótulos'],
    ['route', 'Rota']
];

let layerControlSeq = 0;

export function mountLayerControls(host, onChange) {
    if (!host || typeof document === 'undefined') return null;
    const layers = readLayerVisibility();
    const box = document.createElement('div');
    box.className = 'map-layers';
    box.setAttribute('role', 'group');
    box.setAttribute('aria-label', 'Camadas');
    const optionsId = `map-layer-options-${layerControlSeq += 1}`;
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'map-layers-toggle';
    toggle.textContent = 'Camadas';
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-controls', optionsId);
    const options = document.createElement('div');
    options.className = 'map-layers-options';
    options.id = optionsId;
    box.append(toggle, options);
    box.addEventListener('pointerdown', (event) => event.stopPropagation());
    toggle.addEventListener('click', () => {
        const open = box.classList.toggle('is-open');
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    const inputs = {};
    FIELDS.forEach(([key, label]) => {
        const wrap = document.createElement('label');
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.checked = layers[key] !== false;
        input.dataset.layer = key;
        const text = document.createElement('span');
        text.textContent = label;
        wrap.append(input, text);
        options.append(wrap);
        inputs[key] = input;
        input.addEventListener('change', () => {
            const next = saveLayerVisibility(readForm());
            if (typeof onChange === 'function') onChange(next);
        });
    });
    host.append(box);

    const compass = mountCompass(host);

    function destroy() {
        if (compass) compass.destroy();
        box.remove();
    }

    function readForm() {
        const next = {};
        FIELDS.forEach(([key]) => {
            next[key] = Boolean(inputs[key] && inputs[key].checked);
        });
        return next;
    }

    return { layers, box, destroy, compass };
}

function mountCompass(host) {
    const compass = document.createElement('div');
    compass.className = 'map-compass';
    const needle = document.createElement('button');
    needle.type = 'button';
    needle.className = 'map-compass-needle';
    needle.setAttribute('aria-label', 'Bússola. Toque para usar a orientação do aparelho.');
    const mark = document.createElement('span');
    mark.className = 'map-compass-n';
    mark.textContent = 'N';
    mark.setAttribute('aria-hidden', 'true');
    needle.append(mark);
    compass.append(needle);
    host.append(compass);

    const heading = new HeadingProvider();
    let headingDeg = 0;
    let rotationRad = 0;
    let frame = 0;

    function paint() {
        frame = 0;
        const deg = compassNeedleDeg(compassBearingDeg(heading) ?? headingDeg, rotationRad);
        if (deg == null) return;
        needle.style.transform = `rotate(${deg}deg)`;
    }

    function schedule() {
        if (frame) return;
        const raf = typeof requestAnimationFrame === 'function'
            ? requestAnimationFrame
            : (fn) => fn();
        frame = raf(paint);
    }

    const onHeading = heading.onHeading((payload) => {
        const next = payload && Number(payload.headingDeg);
        if (!Number.isFinite(next)) return;
        headingDeg = next;
        schedule();
    });

    function readRotation(event) {
        const raw = event && event.detail != null ? event.detail : host.dataset.planRotation;
        const value = Number(raw);
        if (!Number.isFinite(value)) return;
        rotationRad = value;
        schedule();
    }

    host.addEventListener('pov-plan-rotation', readRotation);
    if (host.dataset && host.dataset.planRotation) readRotation(null);

    const needsGesture = typeof DeviceOrientationEvent !== 'undefined'
        && typeof DeviceOrientationEvent.requestPermission === 'function';
    if (!needsGesture) void heading.start();
    needle.addEventListener('click', () => {
        void heading.start();
    });
    schedule();

    return {
        destroy() {
            if (frame && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(frame);
            frame = 0;
            onHeading();
            host.removeEventListener('pov-plan-rotation', readRotation);
            heading.stop();
            compass.remove();
        }
    };
}
