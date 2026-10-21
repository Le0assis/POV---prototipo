/**
 * Teste de localização no cliente.
 * Passo + heading relativo, parâmetros só de /api/pdr/config.
 * A posição é a projeção por distância acumulada na aresta calibrada.
 */

import { insertTopNav } from '../components/nav.js';
import { getPdrConfig } from '../core/api.js';
import { $, fillSelect, formatNum } from '../core/dom.js';
import { toast } from '../ui/toast.js';
import { HeadingProvider } from '../sensors/heading.js';
import { StepDetector } from '../sensors/step-detector.js';
import { metersToPixels, plantHeadingToScreenDeg } from '../map/coords.js';
import { createFloorMap, resolvePlanImage } from '../map/floor-map.js';
import { renderFloorLayers, contentPixels, createBlueDot } from '../map/layers.js';
import { createPositionTracker } from '../nav/positioning.js';
import { outgoingEdges } from '../route/model.js';
import { nearestCheckpoint, readLocalization } from '../route/localize.js';
import { loadFloorModel } from './floor-model.js';

const heading = new HeadingProvider();
const detector = new StepDetector();

const state = {
    floor: null,
    dot: null,
    model: null,
    pdr: null,
    localization: null,
    running: false,
    walkedM: 0,
    steps: 0,
    edge: null,
    calibBearing: 0,
    offStep: null,
    offHeading: null,
    tracker: null
};

document.addEventListener('DOMContentLoaded', init);
window.addEventListener('pagehide', stopSensors);

async function init() {
    insertTopNav('locate');
    state.floor = createFloorMap($('#floor-map'));
    state.dot = createBlueDot(state.floor);
    $('#loc-start').addEventListener('change', fillEdges);
    $('#loc-start-btn').addEventListener('click', start);
    $('#loc-stop').addEventListener('click', stopSensors);
    $('#loc-recal').addEventListener('click', recalibrate);
    $('#loc-sim').addEventListener('click', simulateStep);
    state.model = await loadFloorModel({ toast });
    try {
        const config = await getPdrConfig();
        state.pdr = config && config.step_length ? config : null;
        state.localization = readLocalization(state.pdr);
        if (state.pdr) detector.setPdrConfig(state.pdr);
    } catch (err) {
        toast(err.message || 'Sem /api/pdr/config. A localização não inicia.', 'erro');
    }
    if (!state.pdr) {
        toast('Sem parâmetros de PDR do servidor.', 'erro');
    }
    paintGoal();
    const placed = state.model.checkpoints
        .filter((cp) => cp.anchor)
        .map((cp) => ({ id: cp.name, label: cp.name }));
    fillSelect($('#loc-start'), placed, 'Checkpoint');
    fillEdges();
    if (state.model.config && state.model.config.plan_image && state.model.config.ready) {
        try {
            await state.floor.setPlan(resolvePlanImage(state.model.config.plan_image));
        } catch (err) {
            toast(err.message || 'Planta indisponível.', 'warn');
        }
    }
    renderFloorLayers(state.floor, state.model, { editable: false });
    state.floor.fitToContent(contentPixels(state.model));
}

function fillEdges() {
    const name = $('#loc-start').value;
    const edges = outgoingEdges(state.model.connections, name);
    const select = $('#loc-edge');
    select.replaceChildren();
    const first = document.createElement('option');
    first.value = '';
    first.textContent = edges.length ? 'Aresta seguinte' : 'Sem aresta saindo daqui';
    select.appendChild(first);
    edges.forEach((edge, index) => {
        const option = document.createElement('option');
        option.value = String(index);
        option.textContent = edge.label;
        select.appendChild(option);
    });
    select._edges = edges;
}

function selectedEdge() {
    const select = $('#loc-edge');
    const edges = select._edges || [];
    const index = Number(select.value);
    if (!Number.isInteger(index) || index < 0 || index >= edges.length) return null;
    return edges[index];
}

async function start() {
    if (state.running) return;
    if (!state.pdr || !state.pdr.step_length) {
        toast('Sem parâmetros de PDR do servidor.', 'erro');
        return;
    }
    if (!state.model.config || !state.model.config.ready) {
        toast('A planta precisa de escala e rotação.', 'warn');
        return;
    }
    const anchor = currentAnchor();
    if (!anchor) {
        toast('Escolha um checkpoint que já tenha posição na planta.', 'warn');
        return;
    }
    const edge = selectedEdge();
    if (!edge) {
        toast('Escolha a aresta seguinte.', 'warn');
        return;
    }

    detector.setPdrConfig(state.pdr);
    const motionOk = await detector.start();
    const orientOk = await heading.start();
    if (!motionOk || !orientOk) {
        toast('Permissão de sensor negada. No desktop, use simular passo.', 'warn');
    }
    state.running = true;
    $('#loc-start-btn').disabled = true;
    $('#loc-stop').disabled = false;
    $('#loc-recal').disabled = false;
    $('#loc-sim').disabled = !Number.isFinite(Number(state.pdr.step_length && state.pdr.step_length.default_m));
    state.offStep = detector.onStep((step) => acceptStep(step.length));
    state.offHeading = heading.onHeading(() => paint());
    restartClient(edge);
    toast('Calibrado neste checkpoint, na direção da aresta seguinte.', 'ok');
}

function recalibrate() {
    if (!state.running) {
        toast('Inicie o teste antes de recalibrar.', 'warn');
        return;
    }
    const edge = selectedEdge();
    const anchor = currentAnchor();
    if (!anchor || !edge) {
        toast('Escolha o checkpoint e a aresta seguinte.', 'warn');
        return;
    }
    restartClient(edge);
    toast(`Posição zerada em ${anchor.name}. Referência: heading da aresta seguinte.`, 'ok');
}

/** Reinício só no aparelho: passos, posição e heading de referência voltam ao checkpoint. */
function restartClient(edge) {
    detector.reset();
    state.edge = edge;
    state.steps = 0;
    state.walkedM = 0;
    state.calibBearing = heading.correctedHeadingDeg ?? heading.headingDeg;
    const start = edge.path[0] || { x: 0, y: 0 };
    state.tracker = createPositionTracker(edge.path);
    state.tracker.anchor({
        x: start.x,
        y: start.y,
        bearingDeg: Number.isFinite(state.calibBearing) ? state.calibBearing : null,
        referenceRad: Number.isFinite(edge.headingRad) ? edge.headingRad : undefined
    });
    paint();
}

function acceptStep(lengthM) {
    if (!state.running || !state.edge) return;
    const length = Number(lengthM);
    if (!Number.isFinite(length) || length <= 0) return;
    state.steps += 1;
    state.walkedM += length;
    if (state.tracker) {
        const bearing = heading.correctedHeadingDeg ?? heading.headingDeg;
        state.tracker.applyStep(length, Number.isFinite(bearing) ? bearing : null);
    }
    paint();
}

function simulateStep() {
    const length = Number(state.pdr && state.pdr.step_length && state.pdr.step_length.default_m);
    if (!state.running || !Number.isFinite(length)) return;
    acceptStep(length);
}

function paint() {
    const edge = state.edge;
    $('#loc-steps').textContent = String(state.steps);
    $('#loc-dist').textContent = `${formatNum(state.walkedM, 2)} m`;
    if (!edge) {
        $('#loc-node').textContent = '—';
        $('#loc-error').textContent = '—';
        $('#loc-edge-label').textContent = 'Nenhuma aresta ativa.';
        return;
    }
    $('#loc-edge-label').textContent = edge.label;
    const anchorNode = state.model.byName.get(edge.source);
    const anchor = anchorNode && anchorNode.anchor;
    const bearing = heading.correctedHeadingDeg ?? heading.headingDeg;
    const pose = state.tracker
        ? state.tracker.poseAt(Number.isFinite(bearing) ? bearing : null)
        : null;
    if (!pose || !anchor || !state.model.config.ready) return;
    const px = metersToPixels(pose.point, anchor, state.model.config);
    if (!px) return;
    state.dot.setPixel(px.x, px.y);
    const screen = plantHeadingToScreenDeg(pose.headingRad, state.model.config.rotation_rad);
    if (screen !== null) state.dot.setHeading(screen);

    const nearest = nearestCheckpoint(px, state.model.checkpoints, state.model.config.px_per_m);
    const windowM = state.localization ? state.localization.snapEndWindowM : null;
    if (!nearest) {
        $('#loc-node').textContent = '—';
        $('#loc-error').textContent = '—';
        return;
    }
    $('#loc-node').textContent = nearest.name;
    const errorEl = $('#loc-error');
    errorEl.textContent = `${formatNum(nearest.errorM, 2)} m`;
    const inside = windowM !== null && nearest.errorM <= windowM;
    errorEl.classList.toggle('goal-ok', inside);
    errorEl.classList.toggle('goal-bad', windowM !== null && !inside);
}

function currentAnchor() {
    const name = $('#loc-start').value;
    return state.model.byName.get(name) || null;
}

function paintGoal() {
    const windowM = state.localization ? state.localization.snapEndWindowM : null;
    $('#loc-goal').textContent = windowM === null
        ? 'Erro em metros até o checkpoint mais próximo. A meta de campo é acertar o checkpoint.'
        : `Meta de campo: checkpoint certo. Erro dentro da janela do servidor (${formatNum(windowM, 2)} m).`;
}

function stopSensors() {
    state.running = false;
    if (state.offStep) state.offStep();
    if (state.offHeading) state.offHeading();
    state.offStep = null;
    state.offHeading = null;
    detector.stop();
    heading.stop();
    const startBtn = $('#loc-start-btn');
    if (startBtn) startBtn.disabled = false;
    const stopBtn = $('#loc-stop');
    if (stopBtn) stopBtn.disabled = true;
    const recal = $('#loc-recal');
    if (recal) recal.disabled = true;
    const sim = $('#loc-sim');
    if (sim) sim.disabled = true;
}
