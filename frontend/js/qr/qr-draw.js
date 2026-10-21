/**
 * Desenho do QR com a cópia local de qrcode-generator (Kazuhiko Arase, MIT).
 * Correção de erro M. O SVG é escalável para a impressão em centímetros.
 */

import qrcode from '../../vendor/qrcode-generator/qrcode.js';

export const QR_ERROR_CORRECTION = 'M';

export function makeQr(text, level = QR_ERROR_CORRECTION) {
    const qr = qrcode(0, level);
    qr.addData(String(text));
    qr.make();
    return qr;
}

export function qrSvg(text, {
    title = '',
    titleId = 'qr-title',
    description = '',
    descriptionId = 'qr-desc',
    level = QR_ERROR_CORRECTION
} = {}) {
    const qr = makeQr(text, level);
    const options = {
        scalable: true,
        margin: 4,
        cellSize: 8
    };
    if (title) options.title = { text: title, id: titleId };
    if (description) options.alt = { text: description, id: descriptionId };
    return qr.createSvgTag(options);
}

/** PNG para o botão de download. Só no navegador, onde existe canvas. */
export function qrPngDataUrl(text, { document: doc, size = 640, level = QR_ERROR_CORRECTION } = {}) {
    const root = doc || (typeof document === 'undefined' ? null : document);
    if (!root || typeof root.createElement !== 'function') {
        throw new Error('Canvas indisponível.');
    }
    const qr = makeQr(text, level);
    const count = qr.getModuleCount();
    const margin = 4;
    const scale = Math.max(1, Math.floor(Number(size) / (count + margin * 2)));
    const dim = (count + margin * 2) * scale;
    const canvas = root.createElement('canvas');
    canvas.width = dim;
    canvas.height = dim;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, dim, dim);
    ctx.fillStyle = '#000000';
    for (let row = 0; row < count; row += 1) {
        for (let col = 0; col < count; col += 1) {
            if (qr.isDark(row, col)) {
                ctx.fillRect((col + margin) * scale, (row + margin) * scale, scale, scale);
            }
        }
    }
    return canvas.toDataURL('image/png');
}
