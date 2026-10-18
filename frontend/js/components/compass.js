/**
 * Componente de Bússola Vetorial (SVG puro, ES module).
 *
 * Exibe o rumo de bússola do pedestre, a direção-alvo da rota e o cone de
 * tolerância de aceitação do grafo.
 */

import { signedDelta, normalizeDeg, unwrap, cardinal } from '../sensors/angles.js';

export const ANGLE_TOLERANCE_DEG = 30;

/**
 * Converte a diferença angular assinada em instrução textual amigável.
 * @param {number} deltaDeg - Diferença assinada (-180, 180] até o alvo.
 * @returns {string}
 */
export function directionText(deltaDeg) {
    if (!Number.isFinite(deltaDeg)) return '--';
    const d = signedDelta(0, deltaDeg);
    const abs = Math.abs(Math.round(d));
    if (abs <= 10) return 'Siga em frente';
    if (abs >= 165) return 'Meia-volta';
    return d > 0 ? `Vire ${abs}° à direita` : `Vire ${abs}° à esquerda`;
}

export class Compass {
    /**
     * @param {HTMLElement} el - Elemento container onde a bússola será renderizada.
     */
    constructor(el) {
        if (!el) {
            throw new Error('[Compass] Elemento container obrigatório');
        }

        this.el = el;
        this._destroyed = false;

        // Estado angular (graus)
        this._targetHeading = null;
        this._headingContinuous = null;
        this._displayedHeading = 0;

        this._targetBearing = null;
        this._needleContinuous = null;
        this._displayedNeedle = 0;

        // Metadados de leitura
        this._readoutTarget = null;
        this._readoutDistanceM = null;
        this._readoutSource = null;

        // Animação e timers
        this._rafId = null;
        this._ariaTimer = null;

        this._onVisibilityChange = () => {
            if (document.hidden) {
                if (this._rafId !== null) {
                    cancelAnimationFrame(this._rafId);
                    this._rafId = null;
                }
            } else if (!this._destroyed && this._rafId === null) {
                this._rafId = requestAnimationFrame(this._loop);
            }
        };

        this._onCalibrateClick = () => {
            this.el.dispatchEvent(new CustomEvent('compass:calibrate', { bubbles: true }));
        };

        this._loop = () => {
            if (this._destroyed) return;

            if (document.hidden) {
                this._rafId = null;
                return;
            }

            this._animateStep();
            this._rafId = requestAnimationFrame(this._loop);
        };

        this._renderBase();
        document.addEventListener('visibilitychange', this._onVisibilityChange);

        this._ariaTimer = setInterval(() => {
            this._updateAriaLabel();
        }, 500);

        this._rafId = requestAnimationFrame(this._loop);
    }

    /**
     * Atualiza o rumo atual (já calibrado / corrigido) em graus.
     * @param {number|null} deg
     */
    setHeading(deg) {
        if (this._destroyed) return;
        if (!Number.isFinite(deg)) {
            this._targetHeading = null;
            this._updateStatusClasses();
            this._updateReadouts();
            return;
        }

        const normalized = normalizeDeg(deg);
        this._targetHeading = normalized;

        if (this._headingContinuous === null) {
            this._headingContinuous = normalized;
            this._displayedHeading = normalized;
        } else {
            this._headingContinuous = unwrap(this._headingContinuous, normalized);
        }

        this._updateStatusClasses();
        this._updateReadouts();
    }

    /**
     * Define o rumo de bússola do alvo (ou null se sem alvo).
     * @param {number|null} bearingDeg
     */
    setTarget(bearingDeg) {
        if (this._destroyed) return;
        if (bearingDeg === null || bearingDeg === undefined || !Number.isFinite(bearingDeg)) {
            this._targetBearing = null;
            if (this._needleGroup) {
                this._needleGroup.style.display = 'none';
            }
        } else {
            this._targetBearing = normalizeDeg(bearingDeg);
            if (this._needleGroup) {
                this._needleGroup.style.display = '';
            }
        }

        this._updateStatusClasses();
        this._updateReadouts();
    }

    /**
     * Define informações contextuais de leitura (alvo, distância, fonte).
     * @param {Object} data
     * @param {string} [data.target]
     * @param {number} [data.distanceM]
     * @param {string} [data.source]
     */
    setReadout({ target, distanceM, source } = {}) {
        if (this._destroyed) return;
        if (target !== undefined) this._readoutTarget = target;
        if (distanceM !== undefined) this._readoutDistanceM = distanceM;
        if (source !== undefined) this._readoutSource = source;
        this._updateReadouts();
    }

    /**
     * Destrói a instância, cancela loops e remove listeners.
     */
    destroy() {
        if (this._destroyed) return;
        this._destroyed = true;

        if (this._rafId !== null) {
            cancelAnimationFrame(this._rafId);
            this._rafId = null;
        }

        if (this._ariaTimer !== null) {
            clearInterval(this._ariaTimer);
            this._ariaTimer = null;
        }

        document.removeEventListener('visibilitychange', this._onVisibilityChange);

        if (this._calibrateBtn) {
            this._calibrateBtn.removeEventListener('click', this._onCalibrateClick);
        }

        if (this.el) {
            this.el.innerHTML = '';
            this.el.classList.remove('is-aligned', 'is-close', 'is-off');
        }
    }

    _animateStep() {
        const prefersReducedMotion = typeof window !== 'undefined'
            && window.matchMedia
            && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        // Interpola rotação da rosa
        if (this._headingContinuous !== null) {
            const diffHeading = this._headingContinuous - this._displayedHeading;
            if (prefersReducedMotion || Math.abs(diffHeading) < 0.05) {
                this._displayedHeading = this._headingContinuous;
            } else {
                this._displayedHeading += diffHeading * 0.2;
            }

            if (this._roseGroup) {
                this._roseGroup.setAttribute('transform', `rotate(${-this._displayedHeading} 150 150)`);
            }
        }

        // Interpola agulha-alvo (relativa ao topo/frente)
        if (this._targetBearing !== null && this._targetHeading !== null) {
            const targetRelative = signedDelta(this._targetHeading, this._targetBearing);

            if (this._needleContinuous === null) {
                this._needleContinuous = targetRelative;
                this._displayedNeedle = targetRelative;
            } else {
                this._needleContinuous = unwrap(this._needleContinuous, normalizeDeg(targetRelative));
            }

            const diffNeedle = this._needleContinuous - this._displayedNeedle;
            if (prefersReducedMotion || Math.abs(diffNeedle) < 0.05) {
                this._displayedNeedle = this._needleContinuous;
            } else {
                this._displayedNeedle += diffNeedle * 0.2;
            }

            if (this._needleGroup) {
                this._needleGroup.setAttribute('transform', `rotate(${this._displayedNeedle} 150 150)`);
            }
        }
    }

    _updateStatusClasses() {
        this.el.classList.remove('is-aligned', 'is-close', 'is-off');

        if (this._targetBearing === null || this._targetHeading === null) {
            this.el.classList.add('is-off');
            return;
        }

        const delta = Math.abs(signedDelta(this._targetHeading, this._targetBearing));
        if (delta <= ANGLE_TOLERANCE_DEG) {
            this.el.classList.add('is-aligned');
        } else if (delta <= 90) {
            this.el.classList.add('is-close');
        } else {
            this.el.classList.add('is-off');
        }
    }

    _updateReadouts() {
        if (!this._headingEl) return;

        // Rumo atual
        if (this._targetHeading !== null) {
            const headingDeg = Math.round(this._targetHeading);
            const card = cardinal(headingDeg);
            this._headingEl.textContent = `${headingDeg}° ${card}`;
        } else {
            this._headingEl.textContent = '--';
        }

        // Delta e instrução
        if (this._deltaEl) {
            if (this._targetBearing !== null && this._targetHeading !== null) {
                const delta = signedDelta(this._targetHeading, this._targetBearing);
                this._deltaEl.textContent = directionText(delta);
            } else {
                this._deltaEl.textContent = 'Aguardando rota...';
            }
        }

        // Segmento / distância
        if (this._targetEl) {
            if (this._readoutTarget) {
                const distStr = typeof this._readoutDistanceM === 'number'
                    ? ` • ${this._readoutDistanceM.toFixed(1)} m`
                    : '';
                this._targetEl.textContent = `${this._readoutTarget}${distStr}`;
            } else {
                this._targetEl.textContent = '--';
            }
        }

        // Fonte do sensor
        if (this._sourceEl) {
            if (this._readoutSource === 'relative') {
                this._sourceEl.textContent = '⚠️ Rumo relativo, calibre';
                this._sourceEl.className = 'compass-source compass-source-warn';
            } else if (this._readoutSource) {
                this._sourceEl.textContent = `Fonte: ${this._readoutSource}`;
                this._sourceEl.className = 'compass-source';
            } else {
                this._sourceEl.textContent = '';
                this._sourceEl.className = 'compass-source';
            }
        }
    }

    _updateAriaLabel() {
        if (!this._svgEl) return;

        let label = 'Bússola de navegação.';
        if (this._targetHeading !== null) {
            label += ` Rumo atual ${Math.round(this._targetHeading)} graus ${cardinal(this._targetHeading)}.`;
        }
        if (this._targetBearing !== null && this._targetHeading !== null) {
            const delta = signedDelta(this._targetHeading, this._targetBearing);
            label += ` ${directionText(delta)}.`;
        }
        this._svgEl.setAttribute('aria-label', label);
    }

    _renderBase() {
        this.el.classList.add('compass-host', 'is-off');

        // Geração dos 72 ticks e rótulos
        const ticksHtml = [];
        const labelsHtml = [];
        const cardinalLabels = { 0: 'N', 90: 'L', 180: 'S', 270: 'O' };

        for (let i = 0; i < 72; i++) {
            const angle = i * 5;
            let len = 5;
            let cls = 'compass-tick';

            if (angle % 30 === 0) {
                len = 12;
                cls = 'compass-tick compass-tick-major';
            } else if (angle % 15 === 0) {
                len = 8;
                cls = 'compass-tick compass-tick-medium';
            }

            ticksHtml.push(
                `<line x1="150" y1="${150 - 130}" x2="150" y2="${150 - 130 + len}" transform="rotate(${angle} 150 150)" class="${cls}" />`
            );

            if (angle % 30 === 0) {
                const rad = (angle * Math.PI) / 180;
                const rText = 104;
                const x = 150 + rText * Math.sin(rad);
                const y = 150 - rText * Math.cos(rad);
                const isCardinal = cardinalLabels[angle] !== undefined;
                const text = isCardinal ? cardinalLabels[angle] : String(angle);
                const textCls = angle === 0
                    ? 'compass-label compass-label-n'
                    : (isCardinal ? 'compass-label compass-label-cardinal' : 'compass-label compass-label-deg');

                labelsHtml.push(
                    `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" class="${textCls}" text-anchor="middle" dominant-baseline="central">${text}</text>`
                );
            }
        }

        // Cone de tolerância de ±30° no topo (88 <= r <= 132)
        // -30° -> x=84, y=35.7; +30° -> x=216, y=35.7 (r=132)
        // -30° -> x=106, y=73.8; +30° -> x=194, y=73.8 (r=88)
        const conePath = 'M 84 35.7 A 132 132 0 0 1 216 35.7 L 194 73.8 A 88 88 0 0 0 106 73.8 Z';

        this.el.innerHTML = `
            <svg class="compass-svg" viewBox="0 0 300 300" role="img" aria-label="Bússola de navegação">
                <defs>
                    <radialGradient id="compass-glow" cx="50%" cy="50%" r="50%">
                        <stop offset="0%" stop-color="var(--cyan, #22d3ee)" stop-opacity="0.2" />
                        <stop offset="100%" stop-color="transparent" stop-opacity="0" />
                    </radialGradient>
                </defs>

                <circle cx="150" cy="150" r="140" class="compass-backdrop" fill="url(#compass-glow)" />

                <!-- Cone de tolerância fixo na direção frontal -->
                <path d="${conePath}" class="compass-cone" />

                <!-- Anéis concêntricos -->
                <circle cx="150" cy="150" r="130" class="compass-ring-outer" />
                <circle cx="150" cy="150" r="88" class="compass-ring-mid" />
                <circle cx="150" cy="150" r="44" class="compass-ring-inner" />

                <!-- Rosa giratória -->
                <g class="compass-rose">
                    ${ticksHtml.join('')}
                    ${labelsHtml.join('')}
                </g>

                <!-- Agulha de rumo do alvo (grupo separado) -->
                <g class="compass-needle" style="display:none">
                    <line x1="150" y1="150" x2="150" y2="40" class="compass-needle-stem" />
                    <polygon points="150,22 141,44 159,44" class="compass-needle-head" />
                </g>

                <!-- Marcador de frente fixo no topo -->
                <polygon points="150,18 143,6 157,6" class="compass-front-marker" />

                <!-- Ponto central com glow -->
                <circle cx="150" cy="150" r="5" class="compass-center-dot" />
            </svg>

            <div class="compass-readouts">
                <div class="compass-readout-row">
                    <div class="compass-heading-val">--</div>
                    <div class="compass-delta-val">Aguardando rota...</div>
                </div>
                <div class="compass-target-val">--</div>
                <div class="compass-source"></div>
                <button type="button" class="btn btn-ghost compass-calibrate-btn">
                    Calibrar (estou de frente para o corredor)
                </button>
            </div>
        `;

        this._svgEl = this.el.querySelector('.compass-svg');
        this._roseGroup = this.el.querySelector('.compass-rose');
        this._needleGroup = this.el.querySelector('.compass-needle');
        this._headingEl = this.el.querySelector('.compass-heading-val');
        this._deltaEl = this.el.querySelector('.compass-delta-val');
        this._targetEl = this.el.querySelector('.compass-target-val');
        this._sourceEl = this.el.querySelector('.compass-source');
        this._calibrateBtn = this.el.querySelector('.compass-calibrate-btn');

        if (this._calibrateBtn) {
            this._calibrateBtn.addEventListener('click', this._onCalibrateClick);
        }
    }
}
