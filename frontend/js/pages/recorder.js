/**
 * Gravador de caminhada. O payload segue RawSampleSchema:
 * timestamp em segundos, accel_*, gyro_* em rad/s, mag_* = alpha/beta/gamma.
 */

import { insertTopNav } from '../components/nav.js';
import { HeadingProvider } from '../sensors/heading.js';
import { StepDetector } from '../sensors/step-detector.js';
import * as api from '../core/api.js';
import { $, escapeHtml, fillSelect, formatNum } from '../core/dom.js';
import { toast } from '../core/toast.js';

const SPARK_MAX = 200;
const MIN_SAMPLES = 20;

const heading = new HeadingProvider();
const detector = new StepDetector();
const samples = [];
const spark = [];
const history = [];

let recording = false;
let liveSteps = 0;
let startedAt = 0;
let clock = null;
let motionHandler = null;

document.addEventListener('DOMContentLoaded', init);

async function init() {
    insertTopNav('map');
    $('#rec-go').addEventListener('click', toggle);
    detector.onStep(() => {
        if (!recording) return;
        liveSteps += 1;
        $('#live-steps').textContent = String(liveSteps);
    });
    window.addEventListener('pagehide', stopSensors);
    renderHistory();
    try {
        const data = await api.getMap();
        const nodes = Array.isArray(data.nodes) ? data.nodes : [];
        fillSelect($('#rec-source'), nodes, 'Origem');
        fillSelect($('#rec-target'), nodes, 'Destino');
    } catch (err) {
        toast(err.message || 'Não foi possível carregar os nós.', 'erro');
    }
}

async function toggle() {
    if (recording) {
        await stopAndSend();
        return;
    }
    const source = $('#rec-source').value;
    const target = $('#rec-target').value;
    if (!source || !target || source === target) {
        toast('Selecione origem e destino diferentes.', 'warn');
        return;
    }

    samples.length = 0;
    spark.length = 0;
    liveSteps = 0;
    $('#sample-count').textContent = '0';
    $('#live-steps').textContent = '0';
    drawSpark();

    const motionOk = await detector.start();
    const orientOk = await heading.start();
    if (!motionOk || !orientOk) {
        toast('Permissão de sensor negada.', 'erro');
        stopSensors();
        return;
    }

    detector.reset();

    motionHandler = (event) => capture(event);
    window.addEventListener('devicemotion', motionHandler);
    recording = true;
    startedAt = Date.now();
    const button = $('#rec-go');
    button.textContent = 'Parar e enviar';
    button.classList.add('is-live');
    clock = setInterval(paintClock, 250);
    paintClock();
    try {
        await api.reset(source);
    } catch (_) {
        /* a gravação segue mesmo se o reset falhar */
    }
}

function capture(event) {
    if (!recording) return;
    const acc = event.accelerationIncludingGravity || event.acceleration;
    if (!acc || acc.x === null || acc.x === undefined) return;

    const rot = event.rotationRate || {};
    const gxDeg = numberOrZero(rot.alpha ?? rot.x);
    const gyDeg = numberOrZero(rot.beta ?? rot.y);
    const gzDeg = numberOrZero(rot.gamma ?? rot.z);
    const gyroX = gxDeg * (Math.PI / 180);
    const gyroY = gyDeg * (Math.PI / 180);
    const gyroZ = gzDeg * (Math.PI / 180);
    const accelX = numberOrZero(acc.x);
    const accelY = numberOrZero(acc.y);
    const accelZ = numberOrZero(acc.z);
    const mag = Math.hypot(accelX, accelY, accelZ);
    const gyroMag = Math.hypot(gyroX, gyroY, gyroZ);
    const orientation = heading.orientation;

    samples.push({
        timestamp: Date.now() / 1000,
        accel_x: accelX,
        accel_y: accelY,
        accel_z: accelZ,
        gyro_x: gyroX,
        gyro_y: gyroY,
        gyro_z: gyroZ,
        mag_x: orientation.alpha,
        mag_y: orientation.beta,
        mag_z: orientation.gamma
    });

    spark.push(mag);
    if (spark.length > SPARK_MAX) spark.shift();
    $('#sample-count').textContent = String(samples.length);
    $('#rec-acc').textContent = `X ${formatNum(accelX, 2)}  Y ${formatNum(accelY, 2)}  Z ${formatNum(accelZ, 2)}  |a| ${formatNum(mag, 2)}`;
    $('#rec-gyro').textContent = `X ${formatNum(gyroX, 2)}  Y ${formatNum(gyroY, 2)}  Z ${formatNum(gyroZ, 2)} rad/s`;
    $('#rec-ori').textContent = `α ${formatNum(orientation.alpha, 0)}°  β ${formatNum(orientation.beta, 0)}°  γ ${formatNum(orientation.gamma, 0)}°`;
    const badge = $('#gyro-badge');
    const active = gyroMag > 0.05;
    badge.textContent = active ? 'Giroscópio ativo' : 'Giroscópio parado';
    badge.classList.toggle('is-on', active);
    drawSpark();
}

async function stopAndSend() {
    const source = $('#rec-source').value;
    const target = $('#rec-target').value;
    const taken = samples.slice();
    const stepsSeen = liveSteps;
    stopSensors();

    if (taken.length < MIN_SAMPLES) {
        toast('Gravação muito curta.', 'warn');
        return;
    }

    try {
        const data = await api.processRaw({ source, target, samples: taken });
        const valid = data.valid === true;
        history.unshift({
            time: new Date().toLocaleTimeString(),
            source,
            target,
            liveSteps: stepsSeen,
            processedSteps: data.steps_count || 0,
            distance: data.distance_m || 0,
            valid,
            message: data.message || (valid ? 'Gravado com sucesso' : 'Trecho descartado')
        });
        renderHistory();
        toast(data.message || (valid ? 'Trecho gravado.' : 'Trecho descartado.'), valid ? 'ok' : 'warn');
    } catch (err) {
        toast(err.message || 'Erro ao enviar a caminhada.', 'erro');
    }
}

function stopSensors() {
    recording = false;
    if (motionHandler) {
        window.removeEventListener('devicemotion', motionHandler);
        motionHandler = null;
    }
    detector.stop();
    heading.stop();
    if (clock !== null) {
        clearInterval(clock);
        clock = null;
    }
    const button = $('#rec-go');
    if (button) {
        button.textContent = 'Gravar caminhada';
        button.classList.remove('is-live');
    }
}

function paintClock() {
    const elapsed = Math.max(0, Date.now() - startedAt);
    const total = Math.floor(elapsed / 1000);
    const mm = String(Math.floor(total / 60)).padStart(2, '0');
    const ss = String(total % 60).padStart(2, '0');
    $('#rec-chrono').textContent = `${mm}:${ss}`;
}

function drawSpark() {
    const canvas = $('#rec-spark');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = '#22d3ee';
    ctx.lineWidth = 2;
    ctx.beginPath();
    const n = Math.max(spark.length, 2);
    spark.forEach((value, index) => {
        const x = (index / (n - 1)) * (w - 8) + 4;
        const y = h - 6 - Math.min(1, Math.max(0, (value - 7) / 8)) * (h - 12);
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    if (spark.length) ctx.stroke();
}

function renderHistory() {
    const host = $('#rec-history');
    host.replaceChildren();
    if (history.length === 0) {
        const empty = document.createElement('p');
        empty.className = 'hint';
        empty.textContent = 'Nenhuma caminhada nesta sessão.';
        host.appendChild(empty);
        return;
    }
    history.forEach((item) => {
        const card = document.createElement('article');
        card.className = `history-card ${item.valid ? 'is-valid' : 'is-invalid'}`;
        card.innerHTML = `
            <div class="history-top">
                <strong>${escapeHtml(item.source)} → ${escapeHtml(item.target)}</strong>
                <span class="badge ${item.valid ? 'ok' : 'warn'}">${item.valid ? 'Válido' : 'Descartado'}</span>
            </div>
            <p>Passos processados ${escapeHtml(item.processedSteps)} · ao vivo ${escapeHtml(item.liveSteps)} · ${escapeHtml(item.distance)} m · ${escapeHtml(item.time)}</p>
            <p>${escapeHtml(item.message)}</p>
        `;
        host.appendChild(card);
    });
}

function numberOrZero(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
}
