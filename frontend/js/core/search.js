/**
 * Busca de destino da folha E2.
 * Sem DOM: acento e maiúsculas saem na comparação, o chip combina com o texto,
 * e a ordem é relevância, distância (só sem texto) e pt-BR.
 */

export const SEARCH_DEBOUNCE_MS = 100;
export const ALL_CHIP = 'todos';
export const OUTROS_CODE = 'outros';
export const OUTROS_LABEL = 'Outros';

export function foldText(value) {
    return String(value ?? '')
        .normalize('NFD')
        .replace(/\p{M}+/gu, '')
        .toLocaleLowerCase('pt-BR');
}

export function destinationCountLabel(count) {
    const total = Number(count) || 0;
    return total === 1 ? '1 destino' : `${total} destinos`;
}

export function debounce(fn, wait = SEARCH_DEBOUNCE_MS) {
    let timer = null;
    function debounced(...args) {
        if (timer != null) clearTimeout(timer);
        timer = setTimeout(() => {
            timer = null;
            fn(...args);
        }, wait);
    }
    debounced.cancel = () => {
        if (timer != null) clearTimeout(timer);
        timer = null;
    };
    return debounced;
}

function positiveScale(value) {
    const px = Number(value);
    return Number.isFinite(px) && px > 0 ? px : null;
}

function readPoint(raw) {
    if (!raw || typeof raw !== 'object') return { pos_x_px: null, pos_y_px: null };
    const directX = Number(raw.pos_x_px);
    const directY = Number(raw.pos_y_px);
    if (raw.pos_x_px != null && raw.pos_y_px != null && Number.isFinite(directX) && Number.isFinite(directY)) {
        return { pos_x_px: directX, pos_y_px: directY };
    }
    const anchor = raw.anchor;
    const anchorX = Number(anchor && anchor.pos_x_px);
    const anchorY = Number(anchor && anchor.pos_y_px);
    if (anchor && anchor.pos_x_px != null && anchor.pos_y_px != null && Number.isFinite(anchorX) && Number.isFinite(anchorY)) {
        return { pos_x_px: anchorX, pos_y_px: anchorY };
    }
    return { pos_x_px: null, pos_y_px: null };
}

function hasPoint(point) {
    return Boolean(point) && Number.isFinite(point.pos_x_px) && Number.isFinite(point.pos_y_px);
}

function categoryCodeOf(raw) {
    const category = raw && raw.category;
    if (!category) return '';
    if (typeof category === 'string') return category.trim();
    return category.code ? String(category.code).trim() : '';
}

function categoryRecord(row) {
    if (!row || row.code == null) return null;
    const code = String(row.code).trim();
    if (!code) return null;
    const named = row.label != null && String(row.label).trim()
        ? row.label
        : (row.name != null ? row.name : code);
    const name = String(named ?? '').trim() || code;
    const orderSource = row.sort_order != null ? row.sort_order : row.order;
    const order = Number(orderSource);
    const icon = row.icon == null ? '' : String(row.icon).trim().toLowerCase();
    return {
        code,
        name,
        order: Number.isFinite(order) ? order : null,
        icon
    };
}

/**
 * `categories` null, ausente ou vazia (404 inclusive) esconde os chips
 * e manda todo checkpoint para Outros. Sem categoria, o item também vai para Outros.
 */
export function buildDestinationCatalog(checkpoints, categories) {
    const known = (Array.isArray(categories) ? categories : [])
        .map(categoryRecord)
        .filter(Boolean);
    const showChips = known.length > 0;
    const byCode = new Map(known.map((category) => [category.code, category]));
    const chips = known.slice().sort((a, b) => {
        const ao = a.order == null ? Number.POSITIVE_INFINITY : a.order;
        const bo = b.order == null ? Number.POSITIVE_INFINITY : b.order;
        if (ao !== bo) return ao - bo;
        return a.name.localeCompare(b.name, 'pt-BR');
    });

    const items = (Array.isArray(checkpoints) ? checkpoints : []).map((raw) => {
        if (!raw || !raw.slug) return null;
        const point = readPoint(raw);
        const code = categoryCodeOf(raw);
        const match = showChips && code ? byCode.get(code) : null;
        const checkpointIcon = raw.category && raw.category.icon
            ? String(raw.category.icon).trim().toLowerCase()
            : '';
        return {
            slug: String(raw.slug),
            name: String(raw.name || raw.slug),
            categoryCode: match ? match.code : OUTROS_CODE,
            categoryName: match ? match.name : OUTROS_LABEL,
            icon: match ? (match.icon || checkpointIcon) : checkpointIcon,
            pos_x_px: point.pos_x_px,
            pos_y_px: point.pos_y_px
        };
    }).filter(Boolean);

    return { showChips, categories: chips, items };
}

/** Metros em linha reta. Sem `px_per_m` ou sem posição, não há distância. */
export function straightLineMeters(from, to, pxPerM) {
    const scale = positiveScale(pxPerM);
    if (scale == null || !hasPoint(from) || !hasPoint(to)) return null;
    return Math.hypot(to.pos_x_px - from.pos_x_px, to.pos_y_px - from.pos_y_px) / scale;
}

export function formatDistanceMeters(meters) {
    if (!Number.isFinite(meters)) return '';
    return `~${Math.round(meters)} m`;
}

function rankOf(item, foldedQuery) {
    const name = foldText(item.name);
    const category = foldText(item.categoryName);
    const nameStarts = name.startsWith(foldedQuery);
    const categoryStarts = category.startsWith(foldedQuery);
    const nameHas = name.includes(foldedQuery);
    const categoryHas = category.includes(foldedQuery);
    if (!nameHas && !categoryHas) return null;
    return nameStarts || categoryStarts ? 0 : 1;
}

function compareDistance(left, right) {
    const leftMissing = left == null;
    const rightMissing = right == null;
    if (leftMissing && rightMissing) return 0;
    if (leftMissing) return 1;
    if (rightMissing) return -1;
    if (left === right) return 0;
    return left < right ? -1 : 1;
}

/**
 * Filtra por texto (qualquer parte do nome ou da categoria) e pelo chip.
 * Com texto: começa com > contém, depois pt-BR.
 * Sem texto e com origem: distância, depois pt-BR.
 * A origem não entra como destino.
 */
export function searchDestinations(items, options = {}) {
    const list = Array.isArray(items) ? items : [];
    const query = String(options.query || '').trim();
    const folded = foldText(query);
    const chip = options.chip || ALL_CHIP;
    const originSlug = options.originSlug ? String(options.originSlug) : '';
    const scale = positiveScale(options.pxPerM);
    const origin = originSlug ? list.find((item) => item && item.slug === originSlug) : null;
    const canDistance = Boolean(origin) && scale != null && hasPoint(origin);

    const results = [];
    list.forEach((item) => {
        if (!item || !item.slug) return;
        if (originSlug && item.slug === originSlug) return;
        if (chip !== ALL_CHIP && item.categoryCode !== chip) return;
        const rank = folded ? rankOf(item, folded) : 0;
        if (rank == null) return;
        const meters = canDistance && hasPoint(item)
            ? straightLineMeters(origin, item, scale)
            : null;
        results.push({
            ...item,
            rank,
            distanceMeters: meters,
            distanceLabel: formatDistanceMeters(meters)
        });
    });

    const byDistance = canDistance && !folded;
    results.sort((a, b) => {
        if (folded && a.rank !== b.rank) return a.rank - b.rank;
        if (byDistance) {
            const distance = compareDistance(a.distanceMeters, b.distanceMeters);
            if (distance !== 0) return distance;
        }
        return a.name.localeCompare(b.name, 'pt-BR');
    });
    return results;
}
