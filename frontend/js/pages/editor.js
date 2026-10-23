/** Cria checkpoints e conexões e grava pos_x_px/pos_y_px. */

import { insertTopNav } from '../components/nav.js';
import * as api from '../core/api.js';
import { $, fillSelect } from '../core/dom.js';
import { whenAdminGranted } from '../core/role-toggle.js';
import { toast } from '../ui/toast.js';
import { degToRad } from '../sensors/angles.js';
import { createFloorMap, resolvePlanImage } from '../map/floor-map.js';
import { renderFloorLayers, contentPixels } from '../map/layers.js';
import { loadFloorModel } from './floor-model.js';
import { addCheckpoint, addManualConnection, patchCheckpointPosition } from './editor-model.js';

const state = {
    floor: null,
    model: null,
    placing: null,
    fitted: false
};

document.addEventListener('DOMContentLoaded', init);

function init() {
    insertTopNav('editor');
    whenAdminGranted(start);
}

async function start() {
    $('#editor-app').classList.remove('hidden');
    state.floor = createFloorMap($('#floor-map'));
    state.floor.map.on('click', onMapClick);
    $('#form-checkpoint').addEventListener('submit', onCheckpoint);
    $('#form-edge').addEventListener('submit', onEdge);
    $('#edge-heading').addEventListener('input', paintHeading);
    paintHeading();
    await reload();
}

async function reload() {
    state.model = await loadFloorModel({ toast, includePath: true });
    fillNodeSelects();
    renderUnplaced();
    if (state.model.config && state.model.config.plan_image) {
        try {
            await state.floor.setPlan(resolvePlanImage(state.model.config.plan_image));
        } catch (err) {
            state.floor.clearPlan();
            toast(err.message || 'Planta indisponível.', 'warn');
        }
    } else {
        state.floor.clearPlan();
    }
    renderFloorLayers(state.floor, state.model, { editable: true, onMove });
    if (!state.fitted) {
        state.floor.fitToContent(contentPixels(state.model));
        state.fitted = true;
    }
}

function paintHeading() {
    const deg = Number($('#edge-heading').value);
    const rad = Number.isFinite(deg) ? degToRad(deg) : 0;
    $('#edge-rad').textContent = rad.toFixed(3);
}

function renderUnplaced() {
    const list = $('#unplaced-list');
    list.replaceChildren();
    const missing = state.model.checkpoints.filter((cp) => !cp.anchor);
    if (missing.length === 0) {
        const item = document.createElement('li');
        item.textContent = 'Todos os checkpoints têm posição.';
        list.appendChild(item);
        return;
    }
    missing.forEach((cp) => {
        const item = document.createElement('li');
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-ghost';
        button.textContent = state.placing === cp.name ? `Posicionando ${cp.name}…` : `Posicionar ${cp.name}`;
        button.addEventListener('click', () => {
            state.placing = cp.name;
            toast(`Clique na planta para fixar "${cp.name}".`, 'info');
            renderUnplaced();
        });
        item.appendChild(button);
        list.appendChild(item);
    });
}

async function onMapClick(event) {
    if (!state.placing) return;
    const pixel = roundPixel(state.floor.latLngToPixel(event.latlng));
    const name = state.placing;
    try {
        await api.updateCheckpointPosition(name, pixel);
        state.placing = null;
        patchCheckpointPosition(state.model, name, pixel);
        paintModel();
        toast(`Posição de "${name}" salva.`, 'ok');
    } catch (err) {
        toast(err.message || 'Falha ao salvar a posição.', 'erro');
    }
}

async function onMove(name, pixel) {
    const rounded = roundPixel(pixel);
    const previous = checkpointPixel(name);
    try {
        await api.updateCheckpointPosition(name, rounded);
        patchCheckpointPosition(state.model, name, rounded);
        paintModel();
        toast(`Posição de "${name}" salva.`, 'ok');
    } catch (err) {
        if (previous) patchCheckpointPosition(state.model, name, previous);
        paintModel();
        toast(err.message || 'Falha ao salvar a posição.', 'erro');
    }
}

async function onCheckpoint(event) {
    event.preventDefault();
    const name = $('#checkpoint-name').value.trim();
    if (!name) return;
    try {
        const saved = await api.saveCheckpoint(name);
        $('#checkpoint-name').value = '';
        const created = (saved && saved.checkpoint) || { name };
        addCheckpoint(state.model, created);
        state.placing = created.name || name;
        fillNodeSelects();
        renderUnplaced();
        toast(`Checkpoint "${name}" criado. Clique na planta para posicionar.`, 'ok');
    } catch (err) {
        toast(err.message || 'Falha ao criar o checkpoint.', 'erro');
    }
}

async function onEdge(event) {
    event.preventDefault();
    const source = $('#edge-source').value;
    const target = $('#edge-target').value;
    const distance = Number($('#edge-distance').value);
    const degrees = Number($('#edge-heading').value);
    if (!source || !target || source === target) {
        toast('Escolha origem e destino diferentes.', 'warn');
        return;
    }
    if (!Number.isFinite(distance) || distance <= 0) {
        toast('Informe uma distância maior que zero.', 'warn');
        return;
    }
    try {
        const heading = degToRad(Number.isFinite(degrees) ? degrees : 0);
        await api.saveEdge({
            source,
            target,
            distance_m: distance,
            heading_rad: heading
        });
        addManualConnection(state.model, { source, target, distance_m: distance, heading_rad: heading });
        paintModel();
        toast('Conexão gravada.', 'ok');
    } catch (err) {
        toast(err.message || 'Falha ao gravar a conexão.', 'erro');
    }
}

function fillNodeSelects() {
    const options = state.model.checkpoints.map((cp) => ({ id: cp.name, label: cp.name }));
    fillSelect($('#edge-source'), options, 'Origem');
    fillSelect($('#edge-target'), options, 'Destino');
}

function paintModel() {
    renderUnplaced();
    renderFloorLayers(state.floor, state.model, { editable: true, onMove });
}

function checkpointPixel(name) {
    const node = state.model && state.model.byName && state.model.byName.get(name);
    if (!node || !node.anchor) return null;
    return { pos_x_px: node.anchor.pos_x_px, pos_y_px: node.anchor.pos_y_px };
}

function roundPixel(pixel) {
    return {
        pos_x_px: Math.round(pixel.pos_x_px * 100) / 100,
        pos_y_px: Math.round(pixel.pos_y_px * 100) / 100
    };
}
