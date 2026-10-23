/**
 * Reproduz uma rota já carregada. A cadência é 1,8 passos/s.
 */

import { normalizeDeg, signedDelta } from '../sensors/angles.js';

const STEP_HZ = 1.8;
const TURN_MS = 600;
const TURN_FRAME_MS = 32;
const JITTER_DEG = 3;

export class RouteSimulator extends EventTarget {
    /**
     * @param {import('./navigation-session.js').NavigationSession} session
     * @param {{onHeading?: Function, sync?: boolean, stepLength?: number, noise?: number}} [options]
     * `noise` é a fração ± em torno do passo (padrão 5%). Use 0 para passo fixo.
     */
    constructor(session, { onHeading, sync = false, stepLength, noise = 0.05 } = {}) {
        super();
        this.session = session;
        this.onHeading = typeof onHeading === 'function' ? onHeading : null;
        this.sync = Boolean(sync);
        this.stepLength = Number(stepLength) > 0 ? Number(stepLength) : session.stepLength;
        this._noise = Number.isFinite(noise) && noise >= 0 ? noise : 0.05;
        this._speed = 1;
        this._running = false;
        this._paused = false;
        this._busy = false;
        this._stepTimer = null;
        this._turnTimer = null;
        this._heading = null;

        this._onSegment = () => {
            const bearing = this.session.bearingTarget(0);
            if (bearing !== null) this._animateTurn(bearing);
        };
        this._onFinish = () => {
            this._clearTimers();
            this._running = false;
            this._paused = false;
        };
    }

    async start() {
        if (this._running) return;
        this._running = true;
        this._paused = false;

        this.session.addEventListener('segment', this._onSegment);
        this.session.addEventListener('finish', this._onFinish);

        const bearing = this.session.bearingTarget(0);
        if (bearing !== null) {
            this._heading = bearing;
            this._publish(bearing);
        }

        if (!this._running) return;
        this._tick();
    }

    pause() {
        if (!this._running || this._paused) return;
        this._paused = true;
        this._clearTimers();
    }

    resume() {
        if (!this._running || !this._paused) return;
        this._paused = false;
        this._scheduleStep();
    }

    stop() {
        this._running = false;
        this._paused = false;
        this._busy = false;
        this._clearTimers();
        this.session.removeEventListener('segment', this._onSegment);
        this.session.removeEventListener('finish', this._onFinish);
    }

    /** @param {1|2|4} value */
    setSpeed(value) {
        if (value !== 1 && value !== 2 && value !== 4) return;
        this._speed = value;
        if (this._running && !this._paused && !this._busy) {
            this._clearStep();
            this._scheduleStep();
        }
    }

    summary() {
        return this.session.summary();
    }

    async _tick() {
        if (!this._running || this._paused || this.session.finished || this._busy) return;
        this._busy = true;

        const swing = (Math.random() * 2 - 1) * this._noise;
        const length = this.stepLength * (1 + swing);
        this._publish(this._heading ?? this.session.bearingTarget(0) ?? 0);

        this.session.registerStep(length);
        this._busy = false;
        if (!this._running || this._paused || this.session.finished) return;
        this._scheduleStep();
    }

    _scheduleStep() {
        this._clearStep();
        const delay = 1000 / (STEP_HZ * this._speed);
        this._stepTimer = setTimeout(() => {
            this._stepTimer = null;
            this._tick();
        }, delay);
    }

    _animateTurn(toDeg) {
        const from = this._heading ?? toDeg;
        const delta = signedDelta(from, toDeg);
        const started = nowMs();
        this._clearTurn();

        const frame = () => {
            if (!this._running) return;
            const t = Math.min(1, (nowMs() - started) / TURN_MS);
            this._heading = normalizeDeg(from + delta * t);
            this._publish(this._heading);
            if (t < 1 && this._running && !this._paused) {
                this._turnTimer = setTimeout(frame, TURN_FRAME_MS);
            } else {
                this._turnTimer = null;
            }
        };
        frame();
    }

    _publish(cleanDeg) {
        const jitter = (Math.random() * 2 - 1) * JITTER_DEG;
        const shown = normalizeDeg((Number.isFinite(cleanDeg) ? cleanDeg : 0) + jitter);
        if (this.onHeading) {
            try {
                this.onHeading(shown);
            } catch (err) {
                console.error('[RouteSimulator] onHeading:', err);
            }
        }
        return shown;
    }

    _fail(err) {
        this.dispatchEvent(domEvent('error', err));
    }

    _clearStep() {
        if (this._stepTimer !== null) {
            clearTimeout(this._stepTimer);
            this._stepTimer = null;
        }
    }

    _clearTurn() {
        if (this._turnTimer !== null) {
            clearTimeout(this._turnTimer);
            this._turnTimer = null;
        }
    }

    _clearTimers() {
        this._clearStep();
        this._clearTurn();
    }
}

function nowMs() {
    if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
        return performance.now();
    }
    return Date.now();
}

function domEvent(type, detail) {
    if (typeof CustomEvent === 'function') return new CustomEvent(type, { detail });
    const event = new Event(type);
    Object.defineProperty(event, 'detail', { value: detail });
    return event;
}
