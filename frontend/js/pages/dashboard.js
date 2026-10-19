/**
 * Dashboard do administrador: mapa, cadastro e rota planejada.
 */

import { insertTopNav } from '../components/nav.js';
import * as api from '../core/api.js';
import { $, escapeHtml, fillSelect, formatNum } from '../core/dom.js';
import { toast } from '../core/toast.js';
import { POLL_MS } from '../core/config.js';

const state = {
    nodes: [],
    edges: [],
    currentNode: null,
    visited: [],
    destination: '',
    planned: [],
    poll: null,
    userMoved: false
};

const view = { scale: 1, panX: 0, panY: 0 };
const pointers = new Map();
let pinch = null;
let rafId = null;
let flow = 0;
let pulse = 0;
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

document.addEventListener('DOMContentLoaded', init);

async function init() {
    insertTopNav('nav');
    const canvas = $('#map-canvas');
    bindForms();
    bindCanvas(canvas);
    new ResizeObserver(() => {
        resizeCanvas();
        if (!state.userMoved) fit();
        draw();
    }).observe($('#map-stage'));
    resizeCanvas();
    await refreshAll();
    state.poll = setInterval(poll, POLL_MS);
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('pagehide', stopLoop, { once: true });
    startLoop();
}

function bindForms() {
    $('#form-checkpoint').addEventListener('submit', onCheckpoint);
    $('#form-edge').addEventListener('submit', onEdge);
    $('#form-reset').addEventListener('submit', onReset);
    $('#edge-heading').addEventListener('input', paintRadians);
    $('#dest-node').addEventListener('change', () => {
        state.destination = $('#dest-node').value;
        planRoute();
    });
    $('#form-dest').addEventListener('submit', (event) => event.preventDefault());
    paintRadians();
}

function bindCanvas(canvas) {
    canvas.addEventListener('wheel', onWheel, { passive: false });
    canvas.addEventListener('pointerdown', onPointerDown);
    canvas.addEventListener('pointermove', onPointerMove);
    canvas.addEventListener('pointerup', onPointerUp);
    canvas.addEventListener('pointercancel', onPointerUp);
    canvas.addEventListener('dblclick', () => {
        state.userMoved = false;
        fit();
        draw();
    });
}

async function refreshAll() {
    await Promise.all([loadMap(), loadRouteCount(), poll()]);
    fillNodes();
    if (!state.userMoved) fit();
    draw();
}

async function loadMap() {
    try {
        const data = await api.getMap();
        state.nodes = Array.isArray(data.nodes) ? data.nodes : [];
        state.edges = Array.isArray(data.edges) ? data.edges : [];
        $('#kpi-nodes').textContent = String(state.nodes.length);
        $('#kpi-edges').textContent = String(state.edges.length);
        setApi(true);
    } catch (err) {
        setApi(false);
        toast(err.message || 'Falha ao carregar o mapa.', 'erro');
    }
}

async function loadRouteCount() {
    try {
        const data = await api.getRoutes();
        const count = Array.isArray(data.routes) ? data.routes.length : 0;
        $('#kpi-routes').textContent = String(count);
    } catch (_) {
        $('#kpi-routes').textContent = '—';
    }
}

async function poll() {
    if (document.hidden) return;
    try {
        const loc = await api.currentLocation();
        setApi(true);
        const node = loc.current_node || null;
        const changed = node !== state.currentNode;
        state.currentNode = node;
        state.visited = Array.isArray(loc.visited_path) ? loc.visited_path : [];
        $('#kpi-node').textContent = node || '—';
        if (changed && state.destination) await planRoute({ quiet: true });
        draw();
    } catch (_) {
        setApi(false);
    }
}

function setApi(online) {
    const el = $('#kpi-api');
    el.textContent = online ? 'online' : 'offline';
    el.classList.toggle('is-on', online);
    el.classList.toggle('is-off', !online);
}

function fillNodes() {
    fillSelect($('#edge-source'), state.nodes, 'Origem');
    fillSelect($('#edge-target'), state.nodes, 'Destino');
    fillSelect($('#reset-node'), state.nodes, 'Nó inicial');
    fillSelect($('#dest-node'), state.nodes, 'Sem destino');
    if (state.destination) $('#dest-node').value = state.destination;
}

function paintRadians() {
    const deg = Number($('#edge-heading').value);
    const rad = Number.isFinite(deg) ? (deg * Math.PI) / 180 : 0;
    $('#edge-rad').textContent = rad.toFixed(3);
}

async function onCheckpoint(event) {
    event.preventDefault();
    const name = $('#checkpoint-name').value.trim();
    if (!name) return;
    try {
        await api.saveCheckpoint(name);
        $('#checkpoint-name').value = '';
        toast(`Checkpoint "${name}" criado.`, 'ok');
        await loadMap();
        fillNodes();
        if (!state.userMoved) fit();
        draw();
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
    const headingRad = (Number.isFinite(degrees) ? degrees : 0) * Math.PI / 180;
    try {
        await api.saveEdge({ source, target, distance_m: distance, heading_rad: headingRad });
        toast('Conexão gravada.', 'ok');
        await loadMap();
        fillNodes();
        if (!state.userMoved) fit();
        if (state.destination) await planRoute();
        draw();
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
        state.currentNode = data.start_node || start;
        state.visited = [state.currentNode];
        $('#kpi-node').textContent = state.currentNode;
        toast(`Sessão reiniciada em ${state.currentNode}.`, 'ok');
        if (state.destination) await planRoute();
        draw();
    } catch (err) {
        toast(err.message || 'Falha ao resetar a sessão.', 'erro');
    }
}

async function planRoute({ quiet = false } = {}) {
    const end = state.destination;
    const start = state.currentNode;
    if (!end || !start || end === start) {
        state.planned = [];
        $('#route-hint').textContent = end && end === start
            ? 'Você já está no destino.'
            : 'A linha verde sai do nó atual.';
        draw();
        return;
    }
    try {
        const data = await api.getCompassRoute(start, end);
        const segments = Array.isArray(data.segments) ? data.segments : [];
        state.planned = segments;
        const sequence = Array.isArray(data.path_sequence) ? data.path_sequence.join(' → ') : '';
        $('#route-hint').textContent = sequence
            ? `${sequence} · ${formatNum(data.total_distance_m, 1)} m`
            : 'Rota calculada.';
        draw();
    } catch (err) {
        state.planned = [];
        $('#route-hint').textContent = 'Sem caminho para esse destino.';
        if (!quiet) toast(err.message || 'Sem caminho.', 'warn');
        draw();
    }
}

function onVisibility() {
    if (document.hidden) {
        stopLoop();
        return;
    }
    startLoop();
    poll();
}

function resizeCanvas() {
    const canvas = $('#map-canvas');
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.round(rect.width * dpr));
    const height = Math.max(1, Math.round(rect.height * dpr));
    if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
    }
}

function fit() {
    const canvas = $('#map-canvas');
    const cssW = canvas.clientWidth || 1;
    const cssH = canvas.clientHeight || 1;
    if (state.nodes.length === 0) {
        view.scale = 1;
        view.panX = cssW / 2;
        view.panY = cssH / 2;
        return;
    }
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    state.nodes.forEach((node) => {
        minX = Math.min(minX, node.x);
        maxX = Math.max(maxX, node.x);
        minY = Math.min(minY, node.y);
        maxY = Math.max(maxY, node.y);
    });
    const worldW = Math.max(maxX - minX, 1);
    const worldH = Math.max(maxY - minY, 1);
    const pad = 56;
    view.scale = Math.min((cssW - pad * 2) / worldW, (cssH - pad * 2) / worldH);
    const drawnW = worldW * view.scale;
    const drawnH = worldH * view.scale;
    view.panX = (cssW - drawnW) / 2 - minX * view.scale;
    view.panY = (cssH - drawnH) / 2 + maxY * view.scale;
}

function toScreen(x, y) {
    return {
        x: view.panX + x * view.scale,
        y: view.panY - y * view.scale
    };
}

function zoomAt(sx, sy, factor) {
    const next = Math.min(400, Math.max(0.05, view.scale * factor));
    const wx = (sx - view.panX) / view.scale;
    const wy = (view.panY - sy) / view.scale;
    view.scale = next;
    view.panX = sx - wx * next;
    view.panY = sy + wy * next;
    state.userMoved = true;
}

function onWheel(event) {
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    const factor = event.deltaY < 0 ? 1.12 : 0.89;
    zoomAt(event.clientX - rect.left, event.clientY - rect.top, factor);
    draw();
}

function onPointerDown(event) {
    event.currentTarget.setPointerCapture(event.pointerId);
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.size === 2) pinch = pointerDistance();
    event.currentTarget.classList.add('is-dragging');
}

function onPointerMove(event) {
    const canvas = event.currentTarget;
    const rect = canvas.getBoundingClientRect();
    const localX = event.clientX - rect.left;
    const localY = event.clientY - rect.top;

    if (pointers.size === 2 && pointers.has(event.pointerId)) {
        pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
        const dist = pointerDistance();
        if (pinch && dist) {
            const mid = pointerMid(rect);
            zoomAt(mid.x, mid.y, dist / pinch);
            pinch = dist;
            draw();
        }
        return;
    }

    if (pointers.size === 1 && pointers.has(event.pointerId)) {
        const prev = pointers.get(event.pointerId);
        view.panX += event.clientX - prev.x;
        view.panY += event.clientY - prev.y;
        pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
        state.userMoved = true;
        draw();
        return;
    }

    showTip(localX, localY);
}

function onPointerUp(event) {
    pointers.delete(event.pointerId);
    if (pointers.size < 2) pinch = null;
    if (pointers.size === 0) event.currentTarget.classList.remove('is-dragging');
}

function pointerDistance() {
    const pts = [...pointers.values()];
    if (pts.length < 2) return 0;
    return Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
}

function pointerMid(rect) {
    const pts = [...pointers.values()];
    return {
        x: (pts[0].x + pts[1].x) / 2 - rect.left,
        y: (pts[0].y + pts[1].y) / 2 - rect.top
    };
}

function nodeById(id) {
    return state.nodes.find((node) => node.id === id) || null;
}

function neighborsOf(id) {
    const names = new Set();
    state.edges.forEach((edge) => {
        if (edge.source === id) names.add(edge.target);
        if (edge.target === id) names.add(edge.source);
    });
    return [...names];
}

function showTip(x, y) {
    const tip = $('#map-tip');
    const hit = hitNode(x, y);
    if (!hit) {
        tip.classList.add('hidden');
        return;
    }
    const neighbors = neighborsOf(hit.id);
    tip.innerHTML = `<strong>${escapeHtml(hit.label || hit.id)}</strong><br>Vizinhos: ${escapeHtml(neighbors.join(', ') || 'nenhum')}`;
    tip.style.left = `${x + 12}px`;
    tip.style.top = `${y + 12}px`;
    tip.classList.remove('hidden');
}

function hitNode(x, y) {
    let found = null;
    let best = 18;
    state.nodes.forEach((node) => {
        const p = toScreen(node.x, node.y);
        const dist = Math.hypot(p.x - x, p.y - y);
        if (dist < best) {
            best = dist;
            found = node;
        }
    });
    return found;
}

function startLoop() {
    if (rafId !== null || reducedMotion) {
        draw();
        return;
    }
    const frame = () => {
        flow = (flow + 0.6) % 24;
        pulse = (pulse + 0.04) % (Math.PI * 2);
        draw();
        rafId = requestAnimationFrame(frame);
    };
    rafId = requestAnimationFrame(frame);
}

function stopLoop() {
    if (rafId !== null) cancelAnimationFrame(rafId);
    rafId = null;
}

function draw() {
    const canvas = $('#map-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    ctx.clearRect(0, 0, w, h);

    ctx.lineWidth = 1.5;
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.55)';
    ctx.fillStyle = '#94a3b8';
    ctx.font = '11px ui-monospace, monospace';
    ctx.textAlign = 'center';
    state.edges.forEach((edge) => {
        const a = nodeById(edge.source);
        const b = nodeById(edge.target);
        if (!a || !b) return;
        const p1 = toScreen(a.x, a.y);
        const p2 = toScreen(b.x, b.y);
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
        const label = `${formatNum(edge.distance_m, 1)} m`;
        ctx.fillText(label, (p1.x + p2.x) / 2, (p1.y + p2.y) / 2 - 6);
    });

    if (state.visited.length > 1) {
        ctx.save();
        ctx.setLineDash([5, 5]);
        ctx.strokeStyle = '#22d3ee';
        ctx.lineWidth = 2;
        ctx.beginPath();
        state.visited.forEach((id, index) => {
            const node = nodeById(id);
            if (!node) return;
            const p = toScreen(node.x, node.y);
            if (index === 0) ctx.moveTo(p.x, p.y);
            else ctx.lineTo(p.x, p.y);
        });
        ctx.stroke();
        ctx.restore();
    }

    if (state.planned.length) {
        ctx.save();
        ctx.strokeStyle = '#22c55e';
        ctx.lineWidth = 3;
        ctx.lineCap = 'round';
        ctx.setLineDash([10, 8]);
        ctx.lineDashOffset = -flow;
        ctx.beginPath();
        state.planned.forEach((segment, index) => {
            const a = nodeById(segment.source);
            const b = nodeById(segment.target);
            if (!a || !b) return;
            const p1 = toScreen(a.x, a.y);
            const p2 = toScreen(b.x, b.y);
            if (index === 0) ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);
        });
        ctx.stroke();
        ctx.restore();
    }

    state.nodes.forEach((node) => {
        const p = toScreen(node.x, node.y);
        const current = node.id === state.currentNode;
        ctx.beginPath();
        ctx.fillStyle = current ? '#22d3ee' : '#8b5cf6';
        ctx.arc(p.x, p.y, current ? 7 : 5, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#f1f5f9';
        ctx.font = '12px Segoe UI, sans-serif';
        ctx.fillText(node.label || node.id, p.x, p.y - 12);
        if (current) {
            const radius = 12 + (reducedMotion ? 4 : 4 + Math.sin(pulse) * 4);
            ctx.beginPath();
            ctx.strokeStyle = 'rgba(34, 211, 238, 0.85)';
            ctx.lineWidth = 2;
            ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
            ctx.stroke();
        }
    });
}
