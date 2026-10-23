/**
 * Seleção dos checkpoints que viram QR.
 * O slug usado na URL é o do contrato. O nome não substitui um slug vazio:
 * sem slug, o ponto aparece na lista e não entra na impressão.
 */

import { adaptCheckpoint } from '../core/checkpoints.js';
import { buildQr } from './qr-format.js';

export const MISSING_SLUG_WARNING = 'sem slug, não é possível gerar';

export function rawSlug(raw) {
    if (!raw || typeof raw !== 'object') return '';
    return raw.slug == null ? '' : String(raw.slug).trim();
}

export function categoryLabel(category) {
    if (!category) return '';
    if (typeof category === 'string') return category.trim();
    const label = category.label == null ? '' : String(category.label).trim();
    if (label) return label;
    return category.code == null ? '' : String(category.code).trim();
}

/** Uma linha da lista. `null` quando não há nome nem slug. */
export function qrCheckpoint(raw) {
    const adapted = adaptCheckpoint(raw);
    if (!adapted) return null;
    const slug = rawSlug(raw);
    const category = adapted.category;
    return {
        slug,
        building_id: adapted.building_id,
        name: adapted.name,
        category,
        categoryLabel: categoryLabel(category),
        missingSlug: !slug
    };
}

export function qrCheckpoints(list) {
    return (Array.isArray(list) ? list : [])
        .map((item, index) => {
            const row = qrCheckpoint(item);
            if (!row) return null;
            return { ...row, key: `${index}:${row.slug || row.name}` };
        })
        .filter(Boolean);
}

/** Filtro por nome ou categoria (rótulo e código). */
export function filterQrCheckpoints(rows, query) {
    const needle = String(query || '').trim().toLowerCase();
    const list = Array.isArray(rows) ? rows : [];
    if (!needle) return list.slice();
    return list.filter((row) => {
        const category = row && row.category;
        const hay = [
            row && row.name,
            row && row.categoryLabel,
            category && category.code,
            category && category.label
        ].filter(Boolean).join(' ').toLowerCase();
        return hay.includes(needle);
    });
}

/**
 * Monta o conteúdo com `buildQr`. Checkpoint sem slug vai para `skipped`
 * com o aviso, e não gera URL.
 */
export function qrJobs(rows) {
    const jobs = [];
    const skipped = [];
    (Array.isArray(rows) ? rows : []).forEach((row) => {
        if (!row || row.missingSlug || !String(row.slug || '').trim()) {
            skipped.push({ ...(row || {}), warning: MISSING_SLUG_WARNING });
            return;
        }
        const text = buildQr({ cp: row.slug, b: row.building_id });
        jobs.push({ ...row, text, warning: '' });
    });
    return { jobs, skipped };
}
