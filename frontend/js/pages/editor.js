/**
 * Única página que cria checkpoints, conexões, grava pos_x_px/pos_y_px
 * e reinicia a sessão do servidor (POST /api/reset, com senha).
 */

import { insertTopNav } from '../components/nav.js';
import * as api from '../core/api.js';
import { $, fillSelect } from '../core/dom.js';
import { toast } from '../ui/toast.js';
import { degToRad, radToDeg } from '../sensors/angles.js';
import { createFloorMap, resolvePlanImage } from '../map/floor-map.js';
import { renderFloorLayers, contentPixels } from '../map/layers.js';
import { loadFloorModel } from './floor-model.js';

const state = {
    floor: null,
    model: null,
    placing: null,
    fitted: false
};

document.addEventListener('DOMContentLoaded', init);

async function init() {
    insertTopNav('editor');
    $('#editor-retry').addEventListener('click', () => { window.location.reload(); });
    const password = await api.ensureEditorPassword();
    if (!password) {
        $('#editor-app').classList.add('hidden');
        $('#editor-locked').classList.remove('hidden');
        return;
    }

    state.floor = createFloorMap($('#floor-map'));
    state.floor.map.on('click', onMapClick);
    $('#form-map-config').addEventListener('submit', onMapConfig);
    $('#form-checkpoint').addEventListener('submit', onCheckpoint);
    $('#form-edge').addEventListener('submit', onEdge);
    $('#form-reset').addEventListener('submit', onReset);
    $('#rotation-deg').addEventListener('input', paintRotation);
    $('#edge-heading').addEventListener('input', paintHeading);
    paintRotation();
    paintHeading();
    await reload();
}

async function reload() {
    state.model = await loadFloorModel({ toast });
    paintConfigForm();
    const options = state.model.checkpoints.map((cp) => ({ id: cp.name, label: cp.name }));
    fillSelect($('#edge-source'), options, 'Origem');
    fillSelect($('#edge-target'), options, 'Destino');
    const resetNode = $('#reset-node');
    const previousReset = resetNode.value;
    fillSelect(resetNode, options, 'Nó inicial');
    if (previousReset) resetNode.value = previousReset;
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

function paintConfigForm() {
    const config = state.model && state.model.config;
    if (!config) return;
    if (config.plan_image) $('#plan-image').value = config.plan_image;
    if (config.px_per_m != null) $('#px-per-m').value = String(config.px_per_m);
    if (config.rotation_rad != null) $('#rotation-deg').value = radToDeg(config.rotation_rad).toFixed(2);
    paintRotation();
}

function paintRotation() {
    const deg = Number($('#rotation-deg').value);
    const rad = Number.isFinite(deg) ? degToRad(deg) : 0;
    $('#rotation-rad').textContent = rad.toFixed(4);
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
    const pixel = state.floor.latLngToPixel(event.latlng);
    const name = state.placing;
    try {
        await api.updateCheckpointPosition(name, roundPixel(pixel));
        state.placing = null;
        toast(`Posição de "${name}" salva.`, 'ok');
        await reload();
    } catch (err) {
        toast(err.message || 'Falha ao salvar a posição.', 'erro');
    }
}

async function onMove(name, pixel) {
    try {
        await api.updateCheckpointPosition(name, roundPixel(pixel));
        toast(`Posição de "${name}" salva.`, 'ok');
        await reload();
    } catch (err) {
        toast(err.message || 'Falha ao salvar a posição.', 'erro');
        await reload();
    }
}

async function onMapConfig(event) {
    event.preventDefault();
    const plan = $('#plan-image').value.trim();
    const rawPx = $('#px-per-m').value.trim();
    const deg = Number($('#rotation-deg').value);
    if (rawPx === '') {
        toast('Falta px_per_m. Sem esse campo o servidor responde 422.', 'warn');
        return;
    }
    const px = Number(rawPx);
    if (!Number.isFinite(px) || px <= 0) {
        toast('px_per_m deve ser um número maior que zero.', 'warn');
        return;
    }
    if (!Number.isFinite(deg)) {
        toast('Informe a rotação.', 'warn');
        return;
    }
    try {
        await api.saveMapConfig({
            plan_image: plan,
            px_per_m: px,
            rotation_rad: degToRad(deg)
        });
        toast('Planta salva.', 'ok');
        state.fitted = false;
        await reload();
    } catch (err) {
        const status = err && err.status;
        const detail = err && err.message ? err.message : 'Falha ao salvar a planta.';
        toast(status === 422 ? `Planta recusada (422): ${detail}` : detail, 'erro');
    }
}

async function onCheckpoint(event) {
    event.preventDefault();
    const name = $('#checkpoint-name').value.trim();
    if (!name) return;
    try {
        await api.saveCheckpoint(name);
        $('#checkpoint-name').value = '';
        state.placing = name;
        toast(`Checkpoint "${name}" criado. Clique na planta para posicionar.`, 'ok');
        await reload();
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
        await api.saveEdge({
            source,
            target,
            distance_m: distance,
            heading_rad: degToRad(Number.isFinite(degrees) ? degrees : 0)
        });
        toast('Conexão gravada.', 'ok');
        await reload();
    } catch (err) {
        toast(err.message || 'Falha ao gravar a conexão.', 'erro');
    }
}

async function onReset(event) {
    event.preventDefault();
    const start = $('#reset-node').value;
    if (!start) {
        toast('Escolha o nó inicial.', 'warn');
        return;
    }
    try {
        const data = await api.reset(start);
        const where = (data && data.start_node) || start;
        toast((data && data.message) || `Sessão reiniciada em ${where}.`, 'ok');
    } catch (err) {
        toast(err.message || 'Falha ao reiniciar a sessão.', 'erro');
    }
}

function roundPixel(pixel) {
    return {
        pos_x_px: Math.round(pixel.pos_x_px * 100) / 100,
        pos_y_px: Math.round(pixel.pos_y_px * 100) / 100
    };
}
