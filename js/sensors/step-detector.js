/**
 * StepDetector — detecção de passos no navegador (espelha as regras do backend).
 *
 * Magnitude da aceleração (com gravidade) → low-pass EMA 0.2 → janela de 1,5 s.
 * Pico: mag > max(9.95, média + 0.12), com subida seguida de descida, período
 * refratário de 330 ms e 0.55 ≤ Δa ≤ 4.5 (Δa = pico − vale da janela).
 * Comprimento do passo (Weinberg): k · Δa^0.25, limitado a [STEP_MIN_M, STEP_MAX_M].
 */

import { WEINBERG_K, STEP_MIN_M, STEP_MAX_M } from '../core/config.js';

const LOW_PASS_ALPHA = 0.2;
const WINDOW_MS = 1500;
const MIN_HEIGHT = 9.95;
const HEIGHT_MARGIN = 0.12;
const REFRACTORY_MS = 330;
const DELTA_A_MIN = 0.55;
const DELTA_A_MAX = 4.5;
const WEINBERG_EXPONENT = 0.25;

export class StepDetector {
    constructor() {
        this._callbacks = new Set();
        this._running = false;
        this._paused = false;
        this._k = WEINBERG_K;
        this._exponent = WEINBERG_EXPONENT;
        this._minM = STEP_MIN_M;
        this._maxM = STEP_MAX_M;
        this._defaultM = null;
        this._refractoryMs = REFRACTORY_MS;
        this._cutoffHz = null;
        this._onMotion = (event) => {
            const acc = event.accelerationIncludingGravity;
            if (!acc || acc.x === null || acc.x === undefined) return;
            this.feed({
                x: Number.isFinite(acc.x) ? acc.x : 0,
                y: Number.isFinite(acc.y) ? acc.y : 0,
                z: Number.isFinite(acc.z) ? acc.z : 0,
                t: Date.now()
            });
        };
        this.reset();
    }

    /**
     * Liga o `devicemotion`. Chamar dentro de gesto do usuário (iOS exige permissão).
     * Resolve `true` se a permissão foi concedida (ou não é necessária).
     */
    async start() {
        if (this._running) {
            if (this._paused) this.resume();
            return true;
        }

        let granted = true;
        if (typeof DeviceMotionEvent !== 'undefined'
            && typeof DeviceMotionEvent.requestPermission === 'function') {
            try {
                granted = (await DeviceMotionEvent.requestPermission()) === 'granted';
            } catch (_) {
                granted = false;
            }
        }
        if (!granted || typeof window === 'undefined') return granted;

        this._running = true;
        this._paused = false;
        window.addEventListener('devicemotion', this._onMotion);
        return true;
    }

    /** Pausa o acelerômetro e limpa a janela, sem esquecer que a permissão já foi dada. */
    pause() {
        if (!this._running || this._paused) return;
        this._paused = true;
        if (typeof window !== 'undefined') {
            window.removeEventListener('devicemotion', this._onMotion);
        }
        this.reset();
    }

    resume() {
        if (!this._running || !this._paused) return;
        this._paused = false;
        if (typeof window !== 'undefined') {
            window.addEventListener('devicemotion', this._onMotion);
        }
    }

    stop() {
        if (typeof window !== 'undefined') {
            window.removeEventListener('devicemotion', this._onMotion);
        }
        this._running = false;
        this._paused = false;
    }

    /** Registra um callback `{length, ts, deltaA}`. Devolve a função de cancelamento. */
    onStep(cb) {
        if (typeof cb !== 'function') return () => {};
        this._callbacks.add(cb);
        return () => this._callbacks.delete(cb);
    }

    /**
     * Aplica os parâmetros de GET /api/pdr/config.
     * Sem esta chamada, o detector mantém o comportamento anterior (rotas/gravador).
     * A tela de localização sempre chama isto e não usa constantes próprias.
     */
    setPdrConfig(pdr) {
        const step = (pdr && pdr.step_length) || {};
        const det = (pdr && pdr.step_detection) || {};
        const num = (value) => {
            const n = Number(value);
            return Number.isFinite(n) ? n : null;
        };
        const k = num(step.k);
        const exponent = num(step.exponent);
        const minM = num(step.min_m);
        const maxM = num(step.max_m);
        const defaultM = num(step.default_m);
        const minInterval = num(det.min_step_interval_s);
        const cutoff = num(det.lowpass_cutoff_hz);
        if (k !== null) this._k = k;
        if (exponent !== null) this._exponent = exponent;
        if (minM !== null) this._minM = minM;
        if (maxM !== null) this._maxM = maxM;
        if (defaultM !== null) this._defaultM = defaultM;
        if (minInterval !== null) this._refractoryMs = minInterval * 1000;
        if (cutoff !== null) this._cutoffHz = cutoff;
    }

    /** Limpa o estado interno (mantém os callbacks registrados). */
    reset() {
        this._smooth = null;
        this._window = [];
        this._windowSum = 0;
        this._prev2 = null;
        this._prev1 = null;
        this._lastT = null;
        this._lastStepTs = -Infinity;
    }

    /** Processa uma amostra `{x, y, z, t}` (t em ms). Não depende de `window`. */
    feed(sample) {
        if (!sample) return;
        const x = Number(sample.x);
        const y = Number(sample.y);
        const z = Number(sample.z);
        const t = Number.isFinite(sample.t) ? sample.t : Date.now();
        if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return;
        if (this._lastT !== null && t <= this._lastT) return;
        const dtMs = this._lastT === null ? null : t - this._lastT;
        this._lastT = t;

        const raw = Math.sqrt(x * x + y * y + z * z);
        const alpha = this._smoothAlpha(dtMs);
        this._smooth = this._smooth === null
            ? raw
            : this._smooth + alpha * (raw - this._smooth);
        const cur = { v: this._smooth, t };

        // Janela deslizante de 1,5 s.
        this._window.push(cur);
        this._windowSum += cur.v;
        while (this._window.length > 1 && this._window[0].t < t - WINDOW_MS) {
            this._windowSum -= this._window.shift().v;
        }

        // Máximo local em _prev1: subiu de _prev2 e não subiu mais em `cur`.
        const p1 = this._prev1;
        const p2 = this._prev2;
        if (p1 && p2 && p1.v > p2.v && p1.v >= cur.v) {
            this._evaluatePeak(p1);
        }

        this._prev2 = p1;
        this._prev1 = cur;
    }

    _evaluatePeak(peak) {
        const mean = this._windowSum / this._window.length;
        const threshold = Math.max(MIN_HEIGHT, mean + HEIGHT_MARGIN);
        if (peak.v <= threshold) return;
        if (peak.t - this._lastStepTs < this._refractoryMs) return;

        let valley = Infinity;
        for (const s of this._window) {
            if (s.v < valley) valley = s.v;
        }
        const deltaA = peak.v - valley;
        if (deltaA < DELTA_A_MIN || deltaA > DELTA_A_MAX) return;

        const rawLength = this._k * Math.pow(deltaA, this._exponent);
        const fallback = Number.isFinite(this._defaultM) ? this._defaultM : rawLength;
        const chosen = Number.isFinite(rawLength) ? rawLength : fallback;
        const length = Math.min(this._maxM, Math.max(this._minM, chosen));
        this._lastStepTs = peak.t;

        const payload = { length, ts: peak.t, deltaA };
        this._emit(payload);
    }

    _smoothAlpha(dtMs) {
        if (!Number.isFinite(this._cutoffHz) || !(dtMs > 0)) return LOW_PASS_ALPHA;
        const dt = dtMs / 1000;
        return Math.min(1, Math.max(0.01, 1 - Math.exp(-2 * Math.PI * this._cutoffHz * dt)));
    }

    _emit(payload) {
        for (const cb of this._callbacks) {
            try {
                cb(payload);
            } catch (err) {
                console.error('[StepDetector] erro em callback:', err);
            }
        }
    }
}
