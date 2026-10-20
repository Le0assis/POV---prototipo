/**
 * Conversão entre o referencial local da aresta (metros) e pixels da planta.
 *
 * Fórmula do contrato (Missão 02):
 *   p_px = pos_px(source) + px_per_m · R(rotation_rad) · (x, −y)
 *
 * (x, y) é local à origem: x para a direita, y para cima.
 * O −y coloca o vetor no eixo da imagem (y cresce para baixo) antes da rotação.
 * R é a rotação anti-horária. pos_px é a âncora do checkpoint de origem.
 */

export function metersToPixels(point, anchor, mapConfig) {
    const parts = linearParts(point, anchor, mapConfig);
    if (!parts) return null;
    return {
        x: parts.ax + parts.scale * parts.rx,
        y: parts.ay + parts.scale * parts.ry
    };
}

/** Inverso de `metersToPixels`. Devolve metros locais à âncora. */
export function pixelsToMeters(pixel, anchor, mapConfig) {
    const ax = num(anchor && anchor.pos_x_px);
    const ay = num(anchor && anchor.pos_y_px);
    const scale = num(mapConfig && mapConfig.px_per_m);
    const theta = num(mapConfig && mapConfig.rotation_rad);
    const px = num(pixel && (pixel.x ?? pixel.pos_x_px));
    const py = num(pixel && (pixel.y ?? pixel.pos_y_px));
    if (![ax, ay, scale, theta, px, py].every(Number.isFinite) || scale === 0) return null;

    const dx = (px - ax) / scale;
    const dy = (py - ay) / scale;
    const cos = Math.cos(theta);
    const sin = Math.sin(theta);
    const x = cos * dx + sin * dy;
    const yFlipped = -sin * dx + cos * dy;
    return { x, y: -yFlipped };
}

/**
 * Graus CSS (horário, 0 = para cima) de um heading do plano (rad, anti-horário, 0 = +x),
 * depois da mesma rotação da planta. Não converte bússola — isso fica em sensors/angles.js.
 */
export function plantHeadingToScreenDeg(headingRad, rotationRad) {
    const h = Number(headingRad);
    const theta = Number(rotationRad);
    if (!Number.isFinite(h) || !Number.isFinite(theta)) return null;
    const pixel = metersToPixels(
        { x: Math.cos(h), y: Math.sin(h) },
        { pos_x_px: 0, pos_y_px: 0 },
        { px_per_m: 1, rotation_rad: theta }
    );
    if (!pixel) return null;
    const fromEastDeg = Math.atan2(pixel.y, pixel.x) * (180 / Math.PI);
    return fromEastDeg + 90;
}

/** Distância em metros entre dois pixels, com escala uniforme (rotação preserva comprimento). */
export function pixelDistanceMeters(a, b, pxPerM) {
    const scale = num(pxPerM);
    if (!a || !b || !Number.isFinite(scale) || scale === 0) return null;
    const ax = num(a.x ?? a.pos_x_px);
    const ay = num(a.y ?? a.pos_y_px);
    const bx = num(b.x ?? b.pos_x_px);
    const by = num(b.y ?? b.pos_y_px);
    if (![ax, ay, bx, by].every(Number.isFinite)) return null;
    return Math.hypot(ax - bx, ay - by) / scale;
}

function num(value) {
    if (value === null || value === undefined || value === '') return NaN;
    return typeof value === 'number' ? value : Number(value);
}

function linearParts(point, anchor, mapConfig) {
    const x = num(point && point.x);
    const y = num(point && point.y);
    const ax = num(anchor && anchor.pos_x_px);
    const ay = num(anchor && anchor.pos_y_px);
    const scale = num(mapConfig && mapConfig.px_per_m);
    const theta = num(mapConfig && mapConfig.rotation_rad);
    if (![x, y, ax, ay, scale, theta].every(Number.isFinite) || scale === 0) return null;
    const cos = Math.cos(theta);
    const sin = Math.sin(theta);
    const xImg = x;
    const yImg = -y;
    return {
        ax,
        ay,
        scale,
        rx: cos * xImg - sin * yImg,
        ry: sin * xImg + cos * yImg
    };
}
