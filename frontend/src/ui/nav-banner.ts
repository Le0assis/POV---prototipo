/**
 * Faixa de instrução do E4. O aria-live só muda quando o texto muda,
 * para não repetir a mesma frase a cada passo.
 */

import { NO_SENSORS_NOTICE } from '../nav/positioning.js';

export function mountNavBanner(root, { onInstruction } = {} as any) {
    const instruction = document.createElement('p');
    instruction.className = 'nav-instruction';
    instruction.setAttribute('aria-live', 'polite');
    instruction.setAttribute('aria-atomic', 'true');

    const notice = document.createElement('p');
    notice.className = 'nav-notice';
    notice.hidden = true;

    const status = document.createElement('p');
    status.className = 'nav-status';
    status.setAttribute('aria-live', 'polite');
    status.setAttribute('aria-atomic', 'true');
    status.hidden = true;

    root.classList.add('nav-banner');
    root.replaceChildren(instruction, status, notice);

    let recalcAlong = null;

    function show() {
        root.hidden = false;
    }

    function hide() {
        root.hidden = true;
        recalcAlong = null;
        status.hidden = true;
        status.textContent = '';
        notice.hidden = true;
        notice.textContent = '';
        if (instruction.textContent) {
            instruction.textContent = '';
            if (typeof onInstruction === 'function') onInstruction('');
        }
    }

    function setInstruction(text) {
        const next = text || '';
        if (instruction.textContent === next) return;
        instruction.textContent = next;
        if (typeof onInstruction === 'function') onInstruction(next);
    }

    function setSensors(fallback) {
        notice.hidden = !fallback;
        notice.textContent = fallback ? NO_SENSORS_NOTICE : '';
    }

    function announceRecalculated(alongM) {
        status.hidden = false;
        status.textContent = 'Rota recalculada';
        recalcAlong = Number(alongM) || 0;
        show();
    }

    function syncRecalc(alongM) {
        if (recalcAlong === null || status.hidden) return;
        if (Math.abs((Number(alongM) || 0) - recalcAlong) > 3) {
            status.hidden = true;
            status.textContent = '';
            recalcAlong = null;
        }
    }

    hide();
    return { show, hide, setInstruction, setSensors, announceRecalculated, syncRecalc, element: root };
}
