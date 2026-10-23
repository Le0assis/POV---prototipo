/**
 * Encaixe numa polilinha.
 * - `projectByAccumulatedDistance`: projeção por distância acumulada (PDR ao vivo).
 * - `snapToPolylines`: ponto mais próximo, para desambiguar geometria.
 */

export function projectByAccumulatedDistance(points, walkedM, edgeLengthM) {
    const clean = cleanPoints(points);
    if (clean.length === 0) return null;

    const arc = arcLength(clean);
    const edge = Number(edgeLengthM);
    const walked = Math.max(0, Number(walkedM) || 0);
    const fraction = fractionAlong(walked, edge, arc);
    const targetArcM = fraction * arc;
    const point = pointAtArc(clean, targetArcM);
    const progressM = Number.isFinite(edge) && edge > 0 ? Math.min(walked, edge) : targetArcM;
    const remainingM = Number.isFinite(edge) && edge > 0
        ? Math.max(0, edge - walked)
        : Math.max(0, arc - targetArcM);

    return {
        point,
        progressM,
        arcLengthM: arc,
        fraction,
        remainingM,
        targetArcM,
        overshootM: Number.isFinite(edge) && edge > 0 ? Math.max(0, walked - edge) : 0
    };
}

/** Heading (rad, anti-horário, 0 = +x) da tangente da polilinha na distância andada. */
export function tangentAtDistance(points, walkedM, edgeLengthM) {
    const clean = cleanPoints(points);
    if (clean.length < 2) return null;
    const arc = arcLength(clean);
    const fraction = fractionAlong(Math.max(0, Number(walkedM) || 0), Number(edgeLengthM), arc);
    const target = fraction * arc;
    let acc = 0;
    for (let i = 0; i < clean.length - 1; i += 1) {
        const a = clean[i];
        const b = clean[i + 1];
        const len = Math.hypot(b.x - a.x, b.y - a.y);
        if (acc + len >= target - 1e-9 || i === clean.length - 2) {
            return Math.atan2(b.y - a.y, b.x - a.x);
        }
        acc += len;
    }
    return null;
}

/**
 * Projeta um ponto no segmento mais próximo de cada polilinha e devolve o melhor.
 * `polylines`: [{ id, points: [{x,y}] }]. Distância em unidades do plano (px).
 */
export function snapToPolylines(point, polylines) {
    if (!point || !Array.isArray(polylines)) return null;
    const px = Number(point.x);
    const py = Number(point.y);
    if (!Number.isFinite(px) || !Number.isFinite(py)) return null;

    let best = null;
    polylines.forEach((poly, polylineIndex) => {
        const pts = cleanPoints(poly && poly.points);
        for (let s = 0; s < pts.length - 1; s += 1) {
            const proj = projectOntoSegment({ x: px, y: py }, pts[s], pts[s + 1]);
            if (!best || proj.distance < best.distance) {
                best = {
                    point: proj.point,
                    distance: proj.distance,
                    t: proj.t,
                    segmentIndex: s,
                    polylineIndex,
                    id: poly.id
                };
            }
        }
    });
    return best;
}

export function projectOntoSegment(p, a, b) {
    const abx = b.x - a.x;
    const aby = b.y - a.y;
    const len2 = abx * abx + aby * aby;
    if (len2 === 0) {
        return {
            point: { x: a.x, y: a.y },
            t: 0,
            distance: Math.hypot(p.x - a.x, p.y - a.y)
        };
    }
    let t = ((p.x - a.x) * abx + (p.y - a.y) * aby) / len2;
    t = Math.min(1, Math.max(0, t));
    const point = { x: a.x + abx * t, y: a.y + aby * t };
    return { point, t, distance: Math.hypot(p.x - point.x, p.y - point.y) };
}

function fractionAlong(walked, edge, arc) {
    if (Number.isFinite(edge) && edge > 0) return Math.min(1, Math.max(0, walked / edge));
    if (arc > 0) return Math.min(1, walked / arc);
    return 0;
}

function cleanPoints(points) {
    if (!Array.isArray(points)) return [];
    return points
        .map((p) => ({ x: Number(p && p.x), y: Number(p && p.y) }))
        .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
}

function arcLength(points) {
    let total = 0;
    for (let i = 1; i < points.length; i += 1) {
        total += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);
    }
    return total;
}

function pointAtArc(points, distance) {
    if (points.length === 1) return { ...points[0] };
    if (distance <= 0) return { ...points[0] };
    let acc = 0;
    for (let i = 0; i < points.length - 1; i += 1) {
        const a = points[i];
        const b = points[i + 1];
        const len = Math.hypot(b.x - a.x, b.y - a.y);
        if (len === 0) continue;
        if (acc + len >= distance) {
            const t = (distance - acc) / len;
            return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
        }
        acc += len;
    }
    return { ...points[points.length - 1] };
}
