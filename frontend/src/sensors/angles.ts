/**
 * Utilitários de ângulo (puros, sem DOM — testáveis em node).
 *
 * IMPORTANTE sobre referenciais:
 * - O heading do grafo (`heading_rad`) é o yaw do Madgwick: relativo à POSE INICIAL
 *   do aparelho na gravação, NÃO é o Norte magnético. Por isso existe `offsetDeg`:
 *   ele alinha o referencial do grafo ao rumo de bússola medido pelo navegador.
 * - Rumo de bússola (webkitCompassHeading, 360 - alpha) é medido a partir do Norte,
 *   crescendo no sentido horário.
 * - O yaw do backend cresce no sentido anti-horário (ZYX).
 */

/**
 * 'ccw' = o heading do grafo cresce no sentido anti-horário (como o yaw do Madgwick).
 * 'cw'  = o heading do grafo já é um rumo de bússola (horário).
 */
export const HEADING_CONVENTION = 'ccw';

/** Normaliza um ângulo em graus para [0, 360). */
export function normalizeDeg(a) {
    const n = ((a % 360) + 360) % 360;
    return n === 360 ? 0 : n;
}

/** Menor diferença com sinal de `from` até `to`, em (-180, 180]. */
export function signedDelta(from, to) {
    let d = normalizeDeg(to - from);
    if (d > 180) d -= 360;
    return d;
}

export function degToRad(deg) {
    return (deg * Math.PI) / 180;
}

export function radToDeg(rad) {
    return (rad * 180) / Math.PI;
}

/**
 * Média móvel exponencial circular (via seno/cosseno), resultado em [0, 360).
 * Se `prev` for inválido, devolve `next` normalizado.
 */
export function circularEma(prev, next, alpha) {
    if (!Number.isFinite(next)) return Number.isFinite(prev) ? normalizeDeg(prev) : 0;
    if (!Number.isFinite(prev)) return normalizeDeg(next);

    const p = degToRad(prev);
    const n = degToRad(next);
    const s = (1 - alpha) * Math.sin(p) + alpha * Math.sin(n);
    const c = (1 - alpha) * Math.cos(p) + alpha * Math.cos(n);
    return normalizeDeg(radToDeg(Math.atan2(s, c)));
}

/** Rumo de bússola (graus, horário) → yaw do backend em radianos, no intervalo (−π, π]. */
export function bearingToBackendYaw(deg, offsetDeg = 0) {
    const yawDeg = HEADING_CONVENTION === 'ccw'
        ? offsetDeg - deg
        : deg - offsetDeg;
    return degToRad(signedDelta(0, yawDeg));
}

/**
 * Heading relativo à calibração no checkpoint.
 * `bearingDeg` e `calibBearingDeg` são rumos de bússola (horário).
 * `referenceRad` é o `heading_rad` da aresta seguinte (anti-horário, 0 = +x).
 * Um giro horário do aparelho diminui o heading do plano.
 * Esta é a única conversão bússola → referencial do backend.
 */
export function relativeHeadingRad(bearingDeg, calibBearingDeg, referenceRad) {
    const bearing = Number(bearingDeg);
    const calib = Number(calibBearingDeg);
    const reference = Number(referenceRad);
    if (!Number.isFinite(bearing) || !Number.isFinite(calib) || !Number.isFinite(reference)) return null;
    const deltaClockwiseRad = degToRad(signedDelta(calib, bearing));
    return normalizeRad(reference - deltaClockwiseRad);
}

/** Normaliza radianos para (−π, π]. */
export function normalizeRad(rad) {
    const tau = Math.PI * 2;
    let r = rad % tau;
    if (r <= -Math.PI) r += tau;
    if (r > Math.PI) r -= tau;
    return r;
}
