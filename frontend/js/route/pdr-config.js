/**
 * Aceita o /api/pdr/config aninhado da spec e o corpo plano do PR #2
 * (`weinberg_k`, `step_min_m`, `step_max_m`, `min_step_interval_s`, `lowpass_cutoff_hz`).
 * Não inventa k, limites nem corte: só reorganiza o que o servidor mandou.
 * `default_m`, se o servidor não mandar, é a média de min e max.
 */

export function normalizePdrConfig(raw) {
    if (!raw || typeof raw !== 'object') return null;
    if (raw.step_length && typeof raw.step_length === 'object') return raw;

    const k = Number(raw.weinberg_k);
    const minM = Number(raw.step_min_m);
    const maxM = Number(raw.step_max_m);
    if (![k, minM, maxM].every(Number.isFinite)) return null;

    const interval = Number(raw.min_step_interval_s);
    const cutoff = Number(raw.lowpass_cutoff_hz);
    const explicitDefault = Number(raw.default_m);
    return {
        ...raw,
        step_length: {
            model: 'weinberg',
            k,
            min_m: minM,
            max_m: maxM,
            default_m: Number.isFinite(explicitDefault) ? explicitDefault : (minM + maxM) / 2
        },
        step_detection: {
            min_step_interval_s: Number.isFinite(interval) ? interval : undefined,
            lowpass_cutoff_hz: Number.isFinite(cutoff) ? cutoff : undefined
        },
        localization: raw.localization || null
    };
}
