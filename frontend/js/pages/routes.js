/**
 * Página de rotas: lista, teste real e simulação.
 */

import { insertTopNav } from '../components/nav.js';
import { Compass } from '../components/compass.js';
import { HeadingProvider } from '../sensors/heading.js';
import { StepDetector } from '../sensors/step-detector.js';
import { NavigationSession } from '../routes/navigation-session.js';
import { RouteSimulator } from '../routes/route-simulator.js';
import * as api from '../core/api.js';
import { $, escapeHtml, fillSelect, formatNum } from '../core/dom.js';
import { toast, confirmDialog } from '../core/toast.js';
import { STEP_LENGTH_DEFAULT, STORAGE_KEYS, POLL_MS } from '../core/config.js';

const state = {
    nodes: [],
    routes: [],
    stepLength: readStepLength(),
    run: null
};

document.addEventListener('DOMContentLoaded', init);

async function init() {
    insertTopNav('routes');
    const input = $('#step-length');
    if (input) input.value = state.stepLength.toFixed(2);
    bindStatic();
    renderSkeleton();
    await Promise.all([loadNodes(), loadRoutes()]);
    window.addEventListener('pagehide', () => { shutdown(); }, { once: true });
}

function bindStatic() {
    $('#btn-new-route').addEventListener('click', openModal);
    $('#btn-cancel-route').addEventListener('click', closeModal);
    $('#form-new-route').addEventListener('submit', onCreateRoute);
    $('#modal-new-route').addEventListener('click', (event) => {
        if (event.target.id === 'modal-new-route') closeModal();
    });
    $('#step-length').addEventListener('change', onStepLength);
    $('#routes-list').addEventListener('click', onListClick);

    $('#exec-close').addEventListener('click', () => { shutdown(); });
    $('#exec-summary-close').addEventListener('click', () => { shutdown(); });
    $('#exec-finish').addEventListener('click', finishEarly);
    $('#exec-repeat').addEventListener('click', repeatRun);
    $('#exec-play').addEventListener('click', togglePause);
    $('#exec-sync').addEventListener('change', (event) => {
        if (state.run && state.run.simulator) state.run.simulator.sync = event.target.checked;
    });
    document.querySelectorAll('[data-speed]').forEach((button) => {
        button.addEventListener('click', () => setSpeed(Number(button.dataset.speed), button));
    });
    document.addEventListener('keydown', onKeyDown);
}

function onKeyDown(event) {
    if (event.key !== 'Escape') return;
    if (!$('#modal-new-route').classList.contains('hidden')) {
        closeModal();
        return;
    }
    if (state.run) shutdown();
}

async function loadNodes() {
    try {
        const data = await api.getMap();
        state.nodes = Array.isArray(data.nodes) ? data.nodes : [];
        fillSelect($('#new-route-start'), state.nodes, 'Origem');
        fillSelect($('#new-route-end'), state.nodes, 'Destino');
        const saved = localStorage.getItem(STORAGE_KEYS.startPoint);
        if (saved) $('#new-route-start').value = saved;
    } catch (err) {
        toast(err.message || 'Não foi possível carregar os nós.', 'erro');
    }
}

async function loadRoutes() {
    try {
        const data = await api.getRoutes();
        state.routes = Array.isArray(data.routes) ? data.routes : [];
        renderRoutes();
    } catch (err) {
        state.routes = [];
        renderRoutes();
        toast(err.message || 'Não foi possível carregar as rotas.', 'erro');
    }
}

function renderSkeleton() {
    const list = $('#routes-list');
    list.replaceChildren();
    for (let i = 0; i < 3; i += 1) {
        const card = document.createElement('div');
        card.className = 'card skeleton';
        card.style.height = '120px';
        list.appendChild(card);
    }
}

function renderRoutes() {
    const list = $('#routes-list');
    list.replaceChildren();

    if (state.routes.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'card empty';
        empty.innerHTML = `<p>Nenhuma rota salva ainda.</p>`;
        const cta = document.createElement('button');
        cta.type = 'button';
        cta.className = 'btn btn-primary';
        cta.textContent = '+ Criar primeira rota';
        cta.addEventListener('click', openModal);
        empty.appendChild(cta);
        list.appendChild(empty);
        return;
    }

    state.routes.forEach((route) => {
        const expected = Math.round(Number(route.total_distance_m) / state.stepLength);
        const card = document.createElement('article');
        card.className = 'card route-card';
        card.innerHTML = `
            <h2>${escapeHtml(route.name)}</h2>
            <div class="route-path">
                <span class="route-node start">${escapeHtml(route.start_node)}</span>
                <span class="route-arrow">→</span>
                <span class="route-node end">${escapeHtml(route.end_node)}</span>
            </div>
            <div class="route-meta">
                <span class="mono">${formatNum(route.total_distance_m, 1)} m</span>
                <span class="mono">${expected} passos esperados</span>
            </div>
            <div class="route-actions">
                <button type="button" class="btn btn-success" data-action="test" data-id="${escapeHtml(route.id)}">Testar</button>
                <button type="button" class="btn btn-primary" data-action="sim" data-id="${escapeHtml(route.id)}">Simular rota</button>
                <button type="button" class="btn btn-danger" data-action="delete" data-id="${escapeHtml(route.id)}">Excluir</button>
            </div>
        `;
        list.appendChild(card);
    });
}

function onListClick(event) {
    const button = event.target.closest('[data-action]');
    if (!button) return;
    const id = button.dataset.id;
    const action = button.dataset.action;
    if (action === 'delete') {
        removeRoute(id);
        return;
    }
    begin(id, action === 'sim' ? 'sim' : 'test');
}

async function onCreateRoute(event) {
    event.preventDefault();
    const start = $('#new-route-start').value;
    const end = $('#new-route-end').value;
    const name = $('#new-route-name').value.trim();
    if (!start || !end) {
        toast('Escolha origem e destino.', 'warn');
        return;
    }
    if (start === end) {
        toast('Origem e destino precisam ser diferentes.', 'warn');
        return;
    }
    try {
        await api.createRoute({ start_node: start, end_node: end, name: name || undefined });
        localStorage.setItem(STORAGE_KEYS.startPoint, start);
        closeModal();
        $('#new-route-name').value = '';
        toast('Rota salva.', 'ok');
        await loadRoutes();
    } catch (err) {
        toast(err.message || 'Falha ao salvar a rota.', 'erro');
    }
}

async function removeRoute(id) {
    const route = state.routes.find((item) => String(item.id) === String(id));
    const label = route ? route.name : 'esta rota';
    const ok = await confirmDialog(`Excluir "${label}"?`, { okLabel: 'Excluir', danger: true });
    if (!ok) return;
    try {
        await api.deleteRoute(id);
        toast('Rota excluída.', 'ok');
        await loadRoutes();
    } catch (err) {
        toast(err.message || 'Falha ao excluir.', 'erro');
    }
}

function onStepLength() {
    const input = $('#step-length');
    let value = Number(input.value);
    if (!Number.isFinite(value)) value = STEP_LENGTH_DEFAULT;
    value = Math.min(0.95, Math.max(0.4, value));
    input.value = value.toFixed(2);
    state.stepLength = value;
    localStorage.setItem(STORAGE_KEYS.stepLength, String(value));
    renderRoutes();
}

function readStepLength() {
    try {
        const raw = localStorage.getItem(STORAGE_KEYS.stepLength);
        const value = raw === null ? STEP_LENGTH_DEFAULT : Number(raw);
        if (!Number.isFinite(value)) return STEP_LENGTH_DEFAULT;
        return Math.min(0.95, Math.max(0.4, value));
    } catch (_) {
        return STEP_LENGTH_DEFAULT;
    }
}

function openModal() {
    $('#modal-new-route').classList.remove('hidden');
    $('#new-route-start').focus();
}

function closeModal() {
    $('#modal-new-route').classList.add('hidden');
}

async function begin(id, mode) {
    let payload;
    try {
        payload = await api.getRoute(id);
    } catch (err) {
        toast(err.message || 'Não foi possível abrir a rota.', 'erro');
        return;
    }
    const route = payload && payload.route;
    if (!route || !Array.isArray(route.segments) || route.segments.length === 0) {
        toast('Essa rota não tem segmentos.', 'erro');
        return;
    }
    await shutdown();
    const run = {
        mode,
        route,
        session: new NavigationSession(route, { stepLength: state.stepLength }),
        simulator: null,
        heading: mode === 'test' ? new HeadingProvider() : null,
        detector: mode === 'test' ? new StepDetector() : null,
        compass: null,
        poll: null,
        offStep: null,
        offHeading: null,
        lastSource: null
    };
    state.run = run;
    paintOverlay(run);
    $('#exec').classList.remove('hidden');
    run.compass = new Compass($('#exec-compass'));
    $('#exec-compass').addEventListener('compass:calibrate', onCalibrate);

    run.session.addEventListener('update', () => paintProgress(run));
    run.session.addEventListener('finish', () => showSummary(run));

    if (mode === 'sim') {
        run.simulator = new RouteSimulator(run.session, {
            stepLength: state.stepLength,
            sync: $('#exec-sync').checked,
            onHeading: (deg) => {
                if (!state.run || state.run !== run) return;
                run.compass.setHeading(deg);
                run.compass.setTarget(run.session.bearingTarget(0));
            }
        });
        run.simulator.addEventListener('error', (event) => {
            const err = event.detail;
            toast((err && err.message) || 'Falha ao sincronizar. A simulação continua.', 'warn');
        });
        run.simulator.setSpeed(2);
        run.compass.setReadout({ source: 'simulada' });
        await run.simulator.start();
        return;
    }

    const grantedHeading = await run.heading.start();
    const grantedSteps = await run.detector.start();
    if (!grantedHeading || !grantedSteps) {
        toast('Permissão de sensor negada. No desktop, use as setas ← → para o rumo.', 'warn');
    }
    run.offHeading = run.heading.onHeading((sample) => {
        run.lastSource = sample.source;
        const corrected = run.heading.correctedHeadingDeg;
        if (corrected !== null) run.compass.setHeading(corrected);
        run.compass.setReadout({ source: sample.source });
        run.compass.setTarget(run.session.bearingTarget(0));
    });
    run.offStep = run.detector.onStep(async (step) => {
        if (!state.run || state.run !== run || run.session.finished) return;
        run.session.registerStep(step.length);
    });
    startPoll(run);
    paintProgress(run);
}

function startPoll(run) {
    const tick = async () => {
        if (!state.run || state.run !== run || document.hidden) return;
        paintProgress(run);
    };
    run.poll = setInterval(tick, POLL_MS);
}

function paintOverlay(run) {
    const sim = run.mode === 'sim';
    $('#exec-mode').textContent = sim ? 'Simulação' : 'Teste real';
    $('#exec-title').textContent = run.route.name || `${run.route.start_node} → ${run.route.end_node}`;
    $('#exec-controls').classList.toggle('hidden', !sim);
    $('#exec-summary').classList.add('hidden');
    $('#exec-finish').classList.remove('hidden');
    $('#exec-play').textContent = 'Pausar';
    $('#exec-play').setAttribute('aria-pressed', 'true');
    paintProgress(run);
}

function paintProgress(run) {
    if (!state.run || state.run !== run) return;
    const session = run.session;
    const seg = session.currentSegment;
    $('#exec-segment').textContent = seg ? `${seg.source} → ${seg.target}` : 'Rota concluída';
    $('#exec-steps').textContent = `${session.steps} / ${session.expectedSteps}`;
    $('#exec-dist').textContent = `${formatNum(session.distTotal, 1)} / ${formatNum(session.totalDistance, 1)} m`;
    $('#exec-remain').textContent = `${formatNum(session.remainingSegmentM, 1)} m`;

    if (run.compass) {
        run.compass.setTarget(session.bearingTarget(0));
        run.compass.setReadout({
            target: seg ? `${seg.source} → ${seg.target}` : run.route.end_node,
            distanceM: session.remainingSegmentM,
            source: run.mode === 'sim' ? 'simulada' : run.lastSource
        });
    }

    const bar = $('#exec-bar');
    bar.replaceChildren();
    const total = session.totalDistance || 1;
    session.segments.forEach((segment, index) => {
        const piece = document.createElement('i');
        const width = ((Number(segment.distance_m) || 0) / total) * 100;
        piece.style.width = `${width}%`;
        if (session.finished || index < session.segmentIndex) piece.className = 'is-done';
        else if (index === session.segmentIndex) piece.className = 'is-current';
        bar.appendChild(piece);
    });

    const path = nodePath(run.route);
    const here = session.visited[session.visited.length - 1];
    const list = $('#exec-nodes');
    list.replaceChildren();
    path.forEach((name) => {
        const item = document.createElement('li');
        item.textContent = name;
        const seen = session.visited.includes(name);
        if (name === here && !session.finished) item.className = 'is-current';
        else if (seen) item.className = 'is-done';
        list.appendChild(item);
    });
}

function nodePath(route) {
    if (Array.isArray(route.path_sequence) && route.path_sequence.length) return route.path_sequence;
    const names = [route.start_node];
    (route.segments || []).forEach((segment) => names.push(segment.target));
    return names;
}

function showSummary(run) {
    if (!state.run || state.run !== run) return;
    const summary = run.session.summary();
    $('#exec-finish').classList.add('hidden');
    $('#exec-controls').classList.add('hidden');
    const box = $('#exec-summary');
    box.classList.remove('hidden');
    $('#exec-summary-text').textContent =
        `${summary.steps} passos · ${formatNum(summary.distance, 1)} m · ${formatNum(summary.durationS, 1)} s · ${summary.visited.join(' → ')}`;
    if (run.simulator) run.simulator.stop();
    if (run.detector) run.detector.stop();
    stopPoll(run);
}

function finishEarly() {
    const run = state.run;
    if (!run || run.session.finished) return;
    if (run.simulator) run.simulator.stop();
    if (run.detector) run.detector.stop();
    stopPoll(run);
    showSummary(run);
}

async function repeatRun() {
    const run = state.run;
    if (!run) return;
    const { mode, route } = run;
    await shutdown();
    const fresh = state.routes.find((item) => String(item.id) === String(route.id)) || route;
    await begin(fresh.id, mode);
}

function togglePause() {
    const run = state.run;
    if (!run || !run.simulator) return;
    const button = $('#exec-play');
    if (button.getAttribute('aria-pressed') === 'true') {
        run.simulator.pause();
        button.textContent = 'Retomar';
        button.setAttribute('aria-pressed', 'false');
    } else {
        run.simulator.resume();
        button.textContent = 'Pausar';
        button.setAttribute('aria-pressed', 'true');
    }
}

function setSpeed(value, button) {
    if (!state.run || !state.run.simulator) return;
    state.run.simulator.setSpeed(value);
    document.querySelectorAll('[data-speed]').forEach((item) => item.classList.remove('is-on'));
    button.classList.add('is-on');
}

function onCalibrate() {
    const run = state.run;
    if (!run || !run.heading) {
        toast('A calibração vale para o teste real, com o sensor ligado.', 'info');
        return;
    }
    const bearing = run.session.bearingTarget(0);
    if (bearing === null) return;
    const offset = run.heading.calibrate(bearing);
    if (offset === null) {
        toast('Ainda não há leitura de rumo para calibrar.', 'warn');
        return;
    }
    toast('Calibração salva para este aparelho.', 'ok');
    const corrected = run.heading.correctedHeadingDeg;
    if (corrected !== null) run.compass.setHeading(corrected);
}

function stopPoll(run) {
    if (run && run.poll !== null) {
        clearInterval(run.poll);
        run.poll = null;
    }
}

async function shutdown() {
    const run = state.run;
    if (!run) {
        $('#exec').classList.add('hidden');
        return;
    }
    state.run = null;
    $('#exec-compass').removeEventListener('compass:calibrate', onCalibrate);
    if (run.compass) run.compass.destroy();
    if (run.heading) {
        if (run.offHeading) run.offHeading();
        run.heading.stop();
    }
    if (run.detector) {
        if (run.offStep) run.offStep();
        run.detector.stop();
    }
    if (run.simulator) run.simulator.stop();
    stopPoll(run);
    $('#exec').classList.add('hidden');
    const host = $('#exec-compass');
    if (host) host.replaceChildren();
}
