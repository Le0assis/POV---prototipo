/**
 * Um só lugar para a identidade do checkpoint no contrato M03.
 * A leitura pública traz `slug`, `building_id` e `category`.
 * Sem slug, a chave cai no nome. GET /api/categories e
 * GET /api/checkpoints/resolve?b=&cp= (404 quando não existe)
 * passam por aqui antes de chegar na tela.
 */

export function checkpointSlug(raw) {
    if (!raw) return '';
    if (typeof raw === 'string') return raw.trim();
    const slug = raw.slug == null ? '' : String(raw.slug).trim();
    if (slug) return slug;
    return String(raw.name || raw.id || raw.label || '').trim();
}

function categoryOf(value) {
    if (!value) return null;
    if (typeof value === 'string') {
        const code = value.trim();
        return code ? { code, label: code } : null;
    }
    if (typeof value !== 'object') return null;
    const code = value.code == null ? '' : String(value.code).trim();
    if (!code) return null;
    const labelSource = value.label != null ? value.label : value.name;
    const label = labelSource == null ? code : String(labelSource).trim();
    const category = { code, label: label || code };
    const icon = value.icon == null ? '' : String(value.icon).trim();
    if (icon) category.icon = icon;
    return category;
}

function buildingIdOf(value) {
    if (value == null || value === '') return null;
    const id = Number(value);
    return Number.isFinite(id) ? id : null;
}

/** Normaliza um checkpoint. `null` se não houver slug nem nome. */
export function adaptCheckpoint(raw) {
    if (!raw || typeof raw !== 'object') return null;
    const slug = checkpointSlug(raw);
    if (!slug) return null;
    const name = String(raw.name || raw.id || raw.label || slug).trim() || slug;
    return {
        ...raw,
        name,
        slug,
        building_id: buildingIdOf(raw.building_id),
        category: categoryOf(raw.category)
    };
}

export function adaptCheckpoints(list) {
    return (Array.isArray(list) ? list : [])
        .map((item) => adaptCheckpoint(item))
        .filter(Boolean);
}

/** Corpo de GET /api/categories: `{ categories: [...] }` ou a lista. */
export function adaptCategories(payload) {
    const rows = Array.isArray(payload)
        ? payload
        : (payload && Array.isArray(payload.categories) ? payload.categories : []);
    return rows.map((row) => {
        const code = row && row.code != null ? String(row.code).trim() : '';
        if (!code) return null;
        const labelSource = row.label != null ? row.label : row.name;
        const label = labelSource == null ? code : String(labelSource).trim();
        const orderSource = row.sort_order != null ? row.sort_order : row.order;
        const order = Number(orderSource);
        const category = {
            code,
            label: label || code,
            sort_order: Number.isFinite(order) ? order : null
        };
        const icon = row.icon == null ? '' : String(row.icon).trim();
        if (icon) category.icon = icon;
        return category;
    }).filter(Boolean);
}

/** Corpo de GET /api/checkpoints/resolve: `{ checkpoint }` ou o próprio objeto. */
export function adaptResolve(payload) {
    if (!payload || typeof payload !== 'object') return null;
    const raw = payload.checkpoint && typeof payload.checkpoint === 'object'
        ? payload.checkpoint
        : payload;
    return adaptCheckpoint(raw);
}

/** 404 de /api/checkpoints/resolve: o QR não aponta para um checkpoint. */
export function isResolveNotFound(error) {
    return Boolean(error && Number(error.status) === 404);
}
