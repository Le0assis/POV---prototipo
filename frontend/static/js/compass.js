/**
 * Componente de Bússola Reutilizável
 * Usado no modo teste de routes.html
 */

export class Compass {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            console.error(`Container #${containerId} não encontrado para bússola`);
            return;
        }

        this.segments = [];
        this.currentSegmentIndex = 0;
        this.currentYawRad = 0; // Orientação do dispositivo em radianos (0 = Norte)
        this.currentNode = null;
        this.onSegmentChange = options.onSegmentChange || (() => {});
        this.onDestinationReached = options.onDestinationReached || (() => {});
        this.onProgressUpdate = options.onProgressUpdate || (() => {});

        this.render();
        this.bindOrientation();
    }

    render() {
        this.container.innerHTML = `
            <div class="compass-wrapper">
                <div class="compass-circle">
                    <div class="compass-cardinal N">N</div>
                    <div class="compass-cardinal S">S</div>
                    <div class="compass-cardinal E">L</div>
                    <div class="compass-cardinal W">O</div>
                    <div id="compass-arrow" class="compass-arrow"></div>
                </div>
            </div>
            <div class="compass-info">
                <div id="compass-target" class="compass-target">--</div>
                <div id="compass-delta" class="compass-delta">Aguardando rota...</div>
                <div id="compass-status" class="compass-status">Orientação: --</div>
            </div>
        `;

        this.arrowEl = this.container.querySelector('#compass-arrow');
        this.targetEl = this.container.querySelector('#compass-target');
        this.deltaEl = this.container.querySelector('#compass-delta');
        this.statusEl = this.container.querySelector('#compass-status');
    }

    bindOrientation() {
        // DeviceOrientationEvent: alpha = azimute em graus (0 = Norte, horário)
        window.addEventListener('deviceorientation', (event) => {
            const alpha = event.alpha;
            if (alpha !== null && alpha !== undefined) {
                // Converter graus para radianos: 0 = Norte, sentido horário
                this.currentYawRad = (alpha * Math.PI) / 180.0;
                this.updateArrow();

                if (this.statusEl) {
                    this.statusEl.textContent = `Orientação: ${alpha.toFixed(0)}°`;
                }
            }
        });

        // iOS 13+ requer permissão
        if (typeof DeviceOrientationEvent !== 'undefined' && typeof DeviceOrientationEvent.requestPermission === 'function') {
            document.body.addEventListener('click', async () => {
                try {
                    await DeviceOrientationEvent.requestPermission();
                } catch (e) {
                    console.log('Permissão de orientação não concedida:', e);
                }
            }, { once: true });
        }

        // Fallback para desktop: teclas de seta para simular rotação
        window.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft') {
                this.currentYawRad = this.normalizeAngle(this.currentYawRad - Math.PI / 8);
                this.updateArrow();
            } else if (e.key === 'ArrowRight') {
                this.currentYawRad = this.normalizeAngle(this.currentYawRad + Math.PI / 8);
                this.updateArrow();
            }
        });
    }

    setRoute(segments) {
        this.segments = segments || [];
        this.currentSegmentIndex = 0;
        this.updateArrow();
    }

    update(currentNode) {
        this.currentNode = currentNode;
        this.checkSegmentProgress();
        this.updateArrow();
    }

    checkSegmentProgress() {
        if (this.segments.length === 0 || this.currentSegmentIndex >= this.segments.length) return;

        const segment = this.segments[this.currentSegmentIndex];
        // Se o nó atual mudou para o target do segmento atual, avança
        if (this.currentNode === segment.target) {
            this.currentSegmentIndex++;
            this.onSegmentChange(this.currentSegmentIndex, this.segments.length);

            if (this.currentSegmentIndex >= this.segments.length) {
                this.onDestinationReached();
                if (this.deltaEl) {
                    this.deltaEl.textContent = '🎯 Destino alcançado!';
                }
            }
        }
    }

    updateArrow() {
        if (this.segments.length === 0 || this.currentSegmentIndex >= this.segments.length) {
            if (this.targetEl) this.targetEl.textContent = '--';
            if (this.deltaEl) this.deltaEl.textContent = 'Rota não iniciada';
            if (this.arrowEl) this.arrowEl.style.transform = 'translate(-50%, -50%) rotate(0deg)';
            return;
        }

        const segment = this.segments[this.currentSegmentIndex];
        const targetHeading = segment.heading_rad; // Já vem em radianos do backend

        // Delta = target - current (normalizado para [-PI, PI])
        let delta = this.normalizeAngle(targetHeading - this.currentYawRad);

        // Rotacionar a seta (CSS rotate aceita graus)
        const deltaDeg = delta * 180.0 / Math.PI;
        if (this.arrowEl) {
            this.arrowEl.style.transform = `translate(-50%, -50%) rotate(${deltaDeg}deg)`;
        }

        // Atualizar textos
        if (this.targetEl) {
            this.targetEl.textContent = `${segment.source} → ${segment.target} (${segment.heading_deg.toFixed(0)}°)`;
        }

        const directionLabel = this.getDirectionLabel(deltaDeg);

        if (this.deltaEl) {
            this.deltaEl.textContent = `Delta: ${deltaDeg.toFixed(0)}° | ${directionLabel} | Dist: ${segment.distance_m.toFixed(1)}m`;
        }

        // Callback de progresso (para barra de progresso)
        if (this.onProgressUpdate && segment.distance_m > 0) {
            // O progresso real virá do PDR (accumulated_distance_m)
            // Aqui só notificamos o segmento atual
            this.onProgressUpdate({
                segmentIndex: this.currentSegmentIndex,
                totalSegments: this.segments.length,
                currentSegment: segment,
                deltaDeg: deltaDeg,
                directionLabel: directionLabel
            });
        }
    }

    normalizeAngle(angle) {
        while (angle <= -Math.PI) angle += 2 * Math.PI;
        while (angle > Math.PI) angle -= 2 * Math.PI;
        return angle;
    }

    getDirectionLabel(deltaDeg) {
        if (deltaDeg > -22.5 && deltaDeg <= 22.5) return '⬆️ Frente';
        if (deltaDeg > 22.5 && deltaDeg <= 67.5) return '↗️ Diag. Dir.';
        if (deltaDeg > 67.5 && deltaDeg <= 112.5) return '➡️ Direita';
        if (deltaDeg > 112.5 && deltaDeg <= 157.5) return '↘️ Diag. Dir. Tras';
        if (deltaDeg > 157.5 || deltaDeg <= -157.5) return '⬇️ Trás';
        if (deltaDeg > -157.5 && deltaDeg <= -112.5) return '↙️ Diag. Esq. Tras';
        if (deltaDeg > -112.5 && deltaDeg <= -67.5) return '⬅️ Esquerda';
        if (deltaDeg > -67.5 && deltaDeg <= -22.5) return '↖️ Diag. Esq.';
        return '⬆️ Frente';
    }

    // Método para forçar atualização (útil quando currentNode muda via polling)
    refresh() {
        this.updateArrow();
    }
}