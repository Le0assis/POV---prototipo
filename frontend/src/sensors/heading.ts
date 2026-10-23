/**
 * HeadingProvider — rumo de bússola do aparelho (graus, horário a partir do Norte).
 *
 * Prioridade das fontes:
 *   1. event.webkitCompassHeading (iOS)           → source 'webkit'
 *   2. deviceorientationabsolute com (360 - alpha) → source 'absolute'
 *   3. deviceorientation com (360 - alpha)         → source 'relative'
 * Também aceita `injectHeading(deg)` (simulador) e teclado ← → no desktop.
 *
 * O heading do grafo é relativo à pose inicial (não é Norte magnético); o offset de
 * calibração (`offsetDeg`) é somado ao rumo bruto para alinhar o sensor ao referencial
 * do grafo: rumo_corrigido = rumo_bruto + offsetDeg.
 */

import { STORAGE_KEYS } from '../core/config.js';
import { circularEma, normalizeDeg, signedDelta, bearingToBackendYaw } from './angles.js';

const EMA_ALPHA = 0.15;
const KEY_STEP_DEG = 5;

function getScreenAngle() {
    if (typeof screen !== 'undefined' && screen.orientation && typeof screen.orientation.angle === 'number') {
        return screen.orientation.angle;
    }
    if (typeof window !== 'undefined' && typeof window.orientation === 'number') {
        return window.orientation;
    }
    return 0;
}

export class HeadingProvider {
    [key: string]: any;

    constructor() {
        this._callbacks = new Set();
        this._offsetDeg = this._loadOffset();
        this._lastHeadingDeg = null;
        this._ema = null;
        this._started = false;
        this._paused = false;
        this._granted = false;
        this._sensorActive = false;
        this._absoluteSeen = false;
        this._orientation = { alpha: 0, beta: 0, gamma: 0 };

        this._onAbsolute = (event) => {
            this._captureOrientation(event);
            if (event.alpha === null || event.alpha === undefined) return;
            this._absoluteSeen = true;
            this._handleSensor(360 - event.alpha, 'absolute', null);
        };

        this._onOrientation = (event) => {
            this._captureOrientation(event);
            const wk = event.webkitCompassHeading;
            if (typeof wk === 'number' && Number.isFinite(wk)) {
                const acc = typeof event.webkitCompassAccuracy === 'number' ? event.webkitCompassAccuracy : null;
                this._handleSensor(wk, 'webkit', acc);
                return;
            }
            if (this._absoluteSeen) return;
            if (event.alpha === null || event.alpha === undefined) return;
            const source = event.absolute === true ? 'absolute' : 'relative';
            this._handleSensor(360 - event.alpha, source, null);
        };

        this._onKeyDown = (event) => {
            if (this._sensorActive) return;
            if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
            const tag = event.target && event.target.tagName;
            if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
            event.preventDefault();
            const base = this._lastHeadingDeg ?? 0;
            const delta = event.key === 'ArrowRight' ? KEY_STEP_DEG : -KEY_STEP_DEG;
            this.injectHeading(base + delta);
        };
    }

    /**
     * Inicia a escuta. Deve ser chamado dentro de um gesto do usuário (iOS exige
     * permissão). Resolve `true` se a permissão foi concedida (ou não é necessária).
     */
    async start() {
        if (this._started) {
            if (this._paused) this.resume();
            return this._granted !== false;
        }

        let granted = true;
        const orientationEvent = DeviceOrientationEvent as any;
        if (typeof DeviceOrientationEvent !== 'undefined'
            && typeof orientationEvent.requestPermission === 'function') {
            try {
                granted = (await orientationEvent.requestPermission()) === 'granted';
            } catch (_) {
                granted = false;
            }
        }

        this._granted = granted;
        this._started = true;
        this._paused = false;
        if (typeof window === 'undefined') return granted;

        if (granted) this._attachOrientation();
        window.addEventListener('keydown', this._onKeyDown);
        return granted;
    }

    /** Tira a escuta de orientação sem perder a calibração nem pedir permissão de novo. */
    pause() {
        if (!this._started || this._paused || this._granted === false) return;
        this._paused = true;
        this._detachOrientation();
    }

    resume() {
        if (!this._started || !this._paused) return;
        this._paused = false;
        if (this._granted) this._attachOrientation();
    }

    /** Para a escuta e remove todos os listeners. */
    stop() {
        this._detachOrientation();
        if (typeof window !== 'undefined') {
            window.removeEventListener('keydown', this._onKeyDown);
        }
        this._started = false;
        this._paused = false;
        this._granted = false;
        this._sensorActive = false;
        this._absoluteSeen = false;
        this._ema = null;
    }

    _attachOrientation() {
        if (typeof window === 'undefined') return;
        window.addEventListener('deviceorientationabsolute', this._onAbsolute);
        window.addEventListener('deviceorientation', this._onOrientation);
    }

    _detachOrientation() {
        if (typeof window === 'undefined') return;
        window.removeEventListener('deviceorientationabsolute', this._onAbsolute);
        window.removeEventListener('deviceorientation', this._onOrientation);
    }

    /** Registra um callback `{headingDeg, source, accuracy}`. Devolve a função de cancelamento. */
    onHeading(cb) {
        if (typeof cb !== 'function') return () => {};
        this._callbacks.add(cb);
        return () => this._callbacks.delete(cb);
    }

    get offsetDeg() {
        return this._offsetDeg;
    }

    /** Último rumo bruto suavizado (sem offset), ou null. */
    get headingDeg() {
        return this._lastHeadingDeg;
    }

    /** Último rumo com offset de calibração aplicado, ou null. */
    get correctedHeadingDeg() {
        return this._lastHeadingDeg === null
            ? null
            : normalizeDeg(this._lastHeadingDeg + this._offsetDeg);
    }

    /**
     * Calibra: offset = alvo − rumo bruto atual. Salva em localStorage.
     * Devolve o offset, ou null se ainda não há leitura de rumo.
     */
    calibrate(targetBearingDeg) {
        if (this._lastHeadingDeg === null || !Number.isFinite(targetBearingDeg)) return null;
        this._offsetDeg = signedDelta(this._lastHeadingDeg, normalizeDeg(targetBearingDeg));
        this._saveOffset();
        return this._offsetDeg;
    }

    /**
     * Última orientação bruta do aparelho (alpha/beta/gamma), usada no payload
     * de gravação como mag_x/mag_y/mag_z.
     */
    get orientation() {
        return { ...this._orientation };
    }

    /** Yaw (rad, em (-PI, PI]) no referencial do backend, já com o offset aplicado. */
    getYawRadForBackend() {
        const corrected = this.correctedHeadingDeg ?? 0;
        return bearingToBackendYaw(corrected, 0);
    }

    /** Injeta um rumo (graus) sem suavização — simulador e teclado. */
    injectHeading(deg) {
        if (!Number.isFinite(deg)) return;
        this._publish(normalizeDeg(deg), 'injected', null, false);
    }

    _captureOrientation(event) {
        if (!event) return;
        const num = (value) => (Number.isFinite(value) ? value : 0);
        this._orientation = {
            alpha: num(event.alpha),
            beta: num(event.beta),
            gamma: num(event.gamma)
        };
    }

    _handleSensor(rawBearingDeg, source, accuracy) {
        if (!Number.isFinite(rawBearingDeg)) return;
        this._sensorActive = true;
        const compensated = normalizeDeg(rawBearingDeg - getScreenAngle());
        this._publish(compensated, source, accuracy, true);
    }

    _publish(deg, source, accuracy, smooth) {
        const heading = smooth ? circularEma(this._ema, deg, EMA_ALPHA) : deg;
        this._ema = heading;
        this._lastHeadingDeg = heading;

        const payload = { headingDeg: heading, source, accuracy };
        for (const cb of this._callbacks) {
            try {
                cb(payload);
            } catch (err) {
                console.error('[HeadingProvider] erro em callback:', err);
            }
        }
    }

    _loadOffset() {
        try {
            if (typeof localStorage === 'undefined') return 0;
            const raw = localStorage.getItem(STORAGE_KEYS.headingOffset);
            const n = raw === null ? NaN : parseFloat(raw);
            return Number.isFinite(n) ? n : 0;
        } catch (_) {
            return 0;
        }
    }

    _saveOffset() {
        try {
            if (typeof localStorage === 'undefined') return;
            localStorage.setItem(STORAGE_KEYS.headingOffset, String(this._offsetDeg));
        } catch (_) {
            // localStorage indisponível: o offset vale apenas durante a sessão.
        }
    }
}
