/** Caixa de camadas do mapa. O estado fica em localStorage. */

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

    function readForm() {
        const next = {};
        FIELDS.forEach(([key]) => {
            next[key] = Boolean(inputs[key] && inputs[key].checked);
        });
        return next;
    }

    return { layers, box };
}
