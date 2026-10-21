/**
 * NavigationSession — contagem local de uma rota (teste real e simulação).
 *
 * O odômetro do backend zera a cada nó e ignora passos fora do cone, então a
 * distância e os passos exibidos vêm daqui. O backend só confirma o nó.
 */

import { backendHeadingToBearing } from '../sensors/angles.js';

export class NavigationSession extends EventTarget {
    /**
     * @param {object} route rota completa (`segments`, `total_distance_m`, `start_node`)
     * @param {{stepLength?: number}} [options]
     */
    constructor(route, { stepLength = 0.7 } = {}) {
        super();
        this.route = route || {};
        this.stepLength = Number(stepLength) > 0 ? Number(stepLength) : 0.7;
        this.segments = Array.isArray(this.route.segments) ? this.route.segments : [];
        this.segmentIndex = 0;
        this.steps = 0;
        this.distTotal = 0;
        this.distSegment = 0;
        this.visited = this.route.start_node ? [this.route.start_node] : [];
        this.startedAt = nowMs();
        this.finished = this.segments.length === 0;
    }

    /** Soma um passo. O excedente do segmento passa para o próximo. */
    registerStep(lengthM) {
        if (this.finished) return;
        const length = Number(lengthM);
        if (!Number.isFinite(length) || length <= 0) return;

        this.steps += 1;
        this.distTotal += length;
        this.distSegment += length;
        this._emit('step', { steps: this.steps, length, distTotal: this.distTotal });

        while (!this.finished) {
            const seg = this.currentSegment;
            if (!seg) {
                this._complete(0);
                break;
            }
            const need = Number(seg.distance_m) || 0;
            if (this.distSegment + 1e-9 < need) break;
            const overflow = this.distSegment - need;
            this._complete(overflow);
        }

        this._emit('update', this.snapshot());
    }

    /**
     * Se o backend já está no alvo deste segmento (ou de um posterior), avança
     * até lá. O backend vence em caso de divergência; nunca volta.
     */
    syncBackendNode(nodeName) {
        if (this.finished || !nodeName) return;

        let match = -1;
        for (let i = this.segmentIndex; i < this.segments.length; i += 1) {
            if (this.segments[i].target === nodeName) match = i;
        }
        if (match < 0) return;

        while (!this.finished && this.segmentIndex <= match) {
            this._complete(0);
        }
        this._emit('update', this.snapshot());
    }

    get expectedSteps() {
        const total = this.totalDistance;
        if (!(this.stepLength > 0)) return 0;
        return Math.round(total / this.stepLength);
    }

    /** Progresso 0–1 pela distância percorrida sobre a distância da rota. */
    get progress() {
        const total = this.totalDistance;
        if (total <= 0) return this.finished ? 1 : 0;
        return Math.min(1, this.distTotal / total);
    }

    get remainingSegmentM() {
        const seg = this.currentSegment;
        if (!seg || this.finished) return 0;
        return Math.max(0, (Number(seg.distance_m) || 0) - this.distSegment);
    }

    get currentSegment() {
        if (this.segmentIndex < 0 || this.segmentIndex >= this.segments.length) return null;
        return this.segments[this.segmentIndex];
    }

    get totalDistance() {
        const declared = Number(this.route.total_distance_m);
        if (Number.isFinite(declared) && declared > 0) return declared;
        return this.segments.reduce((sum, seg) => sum + (Number(seg.distance_m) || 0), 0);
    }

    /** Rumo de bússola (horário) do segmento atual. */
    bearingTarget(offsetDeg = 0) {
        const seg = this.currentSegment;
        if (!seg || !Number.isFinite(Number(seg.heading_rad))) return null;
        return backendHeadingToBearing(Number(seg.heading_rad), offsetDeg);
    }

    snapshot() {
        return {
            segmentIndex: this.segmentIndex,
            steps: this.steps,
            distTotal: this.distTotal,
            distSegment: this.distSegment,
            visited: [...this.visited],
            finished: this.finished,
            progress: this.progress,
            remainingSegmentM: this.remainingSegmentM,
            expectedSteps: this.expectedSteps,
            currentSegment: this.currentSegment
        };
    }

    summary() {
        return {
            steps: this.steps,
            distance: this.distTotal,
            durationS: Math.max(0, (nowMs() - this.startedAt) / 1000),
            visited: [...this.visited]
        };
    }

    _complete(overflow) {
        const seg = this.currentSegment;
        if (seg && this.visited[this.visited.length - 1] !== seg.target) {
            this.visited.push(seg.target);
        }

        const isLast = this.segmentIndex >= this.segments.length - 1;
        if (isLast) {
            this.distSegment = Number(seg?.distance_m) || this.distSegment;
            this.finished = true;
            this._emit('finish', this.summary());
            return;
        }

        this.segmentIndex += 1;
        this.distSegment = Math.max(0, overflow);
        this._emit('segment', {
            segmentIndex: this.segmentIndex,
            segment: this.currentSegment
        });
    }

    _emit(type, detail) {
        this.dispatchEvent(domEvent(type, detail));
    }
}

function domEvent(type, detail) {
    if (typeof CustomEvent === 'function') return new CustomEvent(type, { detail });
    const event = new Event(type);
    Object.defineProperty(event, 'detail', { value: detail });
    return event;
}

function nowMs() {
    if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
        return performance.now();
    }
    return Date.now();
}
