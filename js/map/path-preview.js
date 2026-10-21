/**
 * Prévia da polilinha local devolvida pelo process-raw.
 * Eixo y matemático (para cima). `t` do path é epoch em segundos.
 */

import { pathPreviewColors } from '../core/colors.js';

export function renderPathPreview(canvas, path) {
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;
    const colors = pathPreviewColors();
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = colors.background;
    ctx.fillRect(0, 0, w, h);

    const pts = (Array.isArray(path) ? path : [])
        .map((p) => ({ x: Number(p && p.x), y: Number(p && p.y) }))
        .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));

    if (pts.length < 2) {
        ctx.fillStyle = colors.muted;
        ctx.font = '12px sans-serif';
        ctx.fillText('Sem polilinha.', 12, 24);
        return;
    }

    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    pts.forEach((p) => {
        minX = Math.min(minX, p.x);
        maxX = Math.max(maxX, p.x);
        minY = Math.min(minY, p.y);
        maxY = Math.max(maxY, p.y);
    });
    const spanX = Math.max(maxX - minX, 0.5);
    const spanY = Math.max(maxY - minY, 0.5);
    const pad = 16;
    const scale = Math.min((w - pad * 2) / spanX, (h - pad * 2) / spanY);

    const toCanvas = (p) => ({
        x: pad + (p.x - minX) * scale,
        y: h - pad - (p.y - minY) * scale
    });

    ctx.strokeStyle = colors.stroke;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.beginPath();
    pts.forEach((p, index) => {
        const s = toCanvas(p);
        if (index === 0) ctx.moveTo(s.x, s.y);
        else ctx.lineTo(s.x, s.y);
    });
    ctx.stroke();

    const start = toCanvas(pts[0]);
    const end = toCanvas(pts[pts.length - 1]);
    ctx.fillStyle = colors.start;
    ctx.beginPath();
    ctx.arc(start.x, start.y, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = colors.end;
    ctx.beginPath();
    ctx.arc(end.x, end.y, 4, 0, Math.PI * 2);
    ctx.fill();
}

/** Duração do path em segundos. `t` é epoch (s); ignora t nulo das arestas manuais. */
export function pathDurationSeconds(path) {
    const ts = (Array.isArray(path) ? path : [])
        .map((p) => Number(p && p.t))
        .filter((t) => Number.isFinite(t));
    if (ts.length < 2) return null;
    return ts[ts.length - 1] - ts[0];
}
