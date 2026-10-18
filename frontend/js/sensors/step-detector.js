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
        if (this._running) return true;

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
        window.addEventListener('devicemotion', this._onMotion);
        return true;
    }

    stop() {
        if (typeof window !== 'undefined') {
            window.removeEventListener('devicemotion', this._onMotion);
        }
        this._running = false;
    }

    /** Registra um callback `{length, ts, deltaA}`. Devolve a função de cancelamento. */
    onStep(cb) {
        if (typeof cb !== 'function') return () => {};
        this._callbacks.add(cb);
        return () => this._callbacks.delete(cb);
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
        this._lastT = t;

        const raw = Math.sqrt(x * x + y * y + z * z);
        this._smooth = this._smooth === null
            ? raw
            : this._smooth + LOW_PASS_ALPHA * (raw - this._smooth);
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
        if (peak.t - this._lastStepTs < REFRACTORY_MS) return;

        let valley = Infinity;
        for (const s of this._window) {
            if (s.v < valley) valley = s.v;
        }
        const deltaA = peak.v - valley;
        if (deltaA < DELTA_A_MIN || deltaA > DELTA_A_MAX) return;

        const raw = WEINBERG_K * Math.pow(deltaA, WEINBERG_EXPONENT);
        const length = Math.min(STEP_MAX_M, Math.max(STEP_MIN_M, raw));
        this._lastStepTs = peak.t;

        const payload = { length, ts: peak.t, deltaA };
        for (const cb of this._callbacks) {
            try {
                cb(payload);
            } catch (err) {
                console.error('[StepDetector] erro em callback:', err);
            }
        }
    }
}
