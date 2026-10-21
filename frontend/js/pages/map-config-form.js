/**
 * Validação do formulário da planta, extraída do editor.
 * px_per_m ausente ou <= 0 mostra a mensagem de 422 antes do PUT.
 */

import { degToRad, radToDeg } from '../sensors/angles.js';

export const PX_MISSING_MESSAGE = 'Falta px_per_m. Sem esse campo o servidor responde 422.';
export const PX_INVALID_MESSAGE = 'px_per_m deve ser um número maior que zero. O servidor responde 422.';

export function validateMapConfigInput({ planImage, rawPx, degrees }) {
    if (String(rawPx ?? '').trim() === '') return { error: PX_MISSING_MESSAGE };
    const px = Number(String(rawPx).trim());
    if (!Number.isFinite(px) || px <= 0) return { error: PX_INVALID_MESSAGE };
    const deg = Number(degrees);
    if (!Number.isFinite(deg)) return { error: 'Informe a rotação.' };
    return {
        value: {
            plan_image: String(planImage ?? '').trim(),
            px_per_m: px,
            rotation_rad: degToRad(deg)
        }
    };
}

export function formatMapConfigSaveError(err) {
    const status = err && err.status;
    const detail = err && err.message ? err.message : 'Falha ao salvar a planta.';
    return status === 422 ? `Planta recusada (422): ${detail}` : detail;
}

export function degreesFromRadians(rad) {
    const deg = radToDeg(Number(rad));
    return Number.isFinite(deg) ? deg.toFixed(2) : '';
}
