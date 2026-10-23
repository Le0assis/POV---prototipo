/** Caixa de camadas do mapa. O estado fica em localStorage. */

import { readLayerVisibility, saveLayerVisibility } from './style.js';

const FIELDS = [
    ['plan', 'Planta'],
    ['recorded', 'Gravados'],
    ['manual', 'Manuais'],
    ['labels', 'Rótulos'],
    ['route', 'Rota']
];

export function mountLayerControls(host, onChange) {
    if (!host || typeof document === 'undefined') return null;
    const layers = readLayerVisibility();
    const box = document.createElement('fieldset');
    box.className = 'map-layers';
    const legend = document.createElement('legend');
    legend.className = 'map-layers-legend';
    legend.textContent = 'Camadas';
    box.append(legend);
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
        box.append(wrap);
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
