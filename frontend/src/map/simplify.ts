/** Douglas-Peucker. A tolerância é em pixels da planta. */

export function pixelTolerance(pxPerM) {
    const scale = Number(pxPerM);
    if (!Number.isFinite(scale) || scale <= 0) return 1.5;
    return Math.max(1.5, scale * 0.25);
}

export function simplifyPath(points, tolerance) {
    const src = (Array.isArray(points) ? points : []).filter(finite);
    const tol = Number(tolerance);
    if (src.length <= 2 || !Number.isFinite(tol) || tol <= 0) return src.slice();
    const keep = new Array(src.length).fill(false);
    keep[0] = true;
    keep[src.length - 1] = true;
    const stack = [[0, src.length - 1]];
    while (stack.length) {
        const pair = stack.pop();
        const start = pair[0];
        const end = pair[1];
        let max = 0;
        let index = -1;
        for (let i = start + 1; i < end; i += 1) {
            const distance = perpendicular(src[i], src[start], src[end]);
            if (distance > max) {
                max = distance;
                index = i;
            }
        }
        if (index !== -1 && max > tol) {
            keep[index] = true;
            stack.push([start, index], [index, end]);
        }
    }
    return src.filter((_, index) => keep[index]);
}

export function pointsUntil(points, fraction) {
    const src = (Array.isArray(points) ? points : []).filter(finite);
    if (src.length === 0) return [];
    const t = Math.max(0, Math.min(1, Number(fraction) || 0));
    if (t <= 0) return [src[0]];
    if (src.length === 1 || t >= 1) return src.slice();
    const lengths = [0];
    for (let i = 1; i < src.length; i += 1) {
        lengths.push(lengths[i - 1] + Math.hypot(src[i].x - src[i - 1].x, src[i].y - src[i - 1].y));
    }
    const total = lengths[lengths.length - 1];
    if (total <= 0) return [src[0]];
    const target = total * t;
    const out = [src[0]];
    for (let i = 1; i < src.length; i += 1) {
        if (lengths[i] < target) {
            out.push(src[i]);
            continue;
        }
        const span = lengths[i] - lengths[i - 1];
        const local = span > 0 ? (target - lengths[i - 1]) / span : 0;
        out.push({
            x: src[i - 1].x + (src[i].x - src[i - 1].x) * local,
            y: src[i - 1].y + (src[i].y - src[i - 1].y) * local
        });
        break;
    }
    return out;
}

export function routeSignature(route) {
    const points = route && Array.isArray(route.points) ? route.points.filter(finite) : [];
    if (points.length < 2) return '';
    const first = points[0];
    const last = points[points.length - 1];
    return `${points.length}:${first.x},${first.y}:${last.x},${last.y}:${route.distance_m || ''}`;
}

function finite(point) {
    return Boolean(point) && Number.isFinite(point.x) && Number.isFinite(point.y);
}

function perpendicular(point, start, end) {
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const length = Math.hypot(dx, dy);
    if (length === 0) return Math.hypot(point.x - start.x, point.y - start.y);
    return Math.abs(dy * point.x - dx * point.y + end.x * start.y - end.y * start.x) / length;
}
