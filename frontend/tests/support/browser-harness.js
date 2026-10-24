/**
 * Servidor estático do frontend e respostas de API para o axe e as capturas.
 */

import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
export const distRoot = path.join(frontendRoot, 'dist');

const MIME = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.mjs': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.json': 'application/json',
    '.woff2': 'font/woff2',
    '.png': 'image/png',
    '.webp': 'image/webp',
    '.ico': 'image/x-icon'
};

export const MOCK_NODES = [
    {
        name: 'Recepção',
        slug: 'recepcao',
        building_id: 1,
        category: { code: 'atendimento', label: 'Atendimento' },
        pos_x_px: 20,
        pos_y_px: 20
    },
    {
        name: 'Sala de aula',
        slug: 'sala',
        building_id: 1,
        category: { code: 'salas', label: 'Salas' },
        pos_x_px: 820,
        pos_y_px: 20
    },
    {
        name: 'Biblioteca',
        slug: 'biblioteca',
        building_id: 1,
        category: { code: 'salas', label: 'Salas' },
        pos_x_px: 20,
        pos_y_px: 400
    },
    {
        name: 'Copa',
        slug: 'copa',
        building_id: 1,
        category: { code: 'alimentacao', label: 'Alimentação' },
        pos_x_px: 420,
        pos_y_px: 400
    },
    {
        name: 'Pátio',
        slug: '   ',
        building_id: 1,
        category: { code: 'saidas', label: 'Saídas' },
        pos_x_px: 100,
        pos_y_px: 100
    }
];

export function startStaticServer(root = frontendRoot) {
    const server = createServer(async (req, res) => {
        try {
            const url = new URL(req.url || '/', 'http://127.0.0.1');
            let rel = decodeURIComponent(url.pathname);
            if (rel.endsWith('/')) rel += 'index.html';
            const file = path.normalize(path.join(root, rel));
            if (!file.startsWith(root)) {
                res.writeHead(403);
                res.end();
                return;
            }
            const body = await readFile(file);
            const ext = path.extname(file);
            res.writeHead(200, { 'content-type': MIME[ext] || 'application/octet-stream' });
            res.end(body);
        } catch (_) {
            res.writeHead(404);
            res.end();
        }
    });
    return new Promise((resolve) => {
        server.listen(0, '127.0.0.1', () => {
            const { port } = server.address();
            resolve({ server, port, origin: `http://127.0.0.1:${port}` });
        });
    });
}

function json(route, body, status = 200) {
    return route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(body)
    });
}

function handleApi(route) {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/auth/check') {
        return route.fulfill({ status: 204, body: '' });
    }
    if (url.pathname === '/api/map') return json(route, { nodes: MOCK_NODES });
    if (url.pathname === '/api/map-config') {
        return json(route, { map_config: { plan_image: '', px_per_m: 20, rotation_rad: 0 } });
    }
    if (url.pathname === '/api/connections') {
        return json(route, {
            connections: [{
                source: 'recepcao',
                target: 'sala',
                distance_m: 40,
                origin: 'manual'
            }]
        });
    }
    if (url.pathname === '/api/categories') {
        return json(route, {
            categories: [
                { code: 'atendimento', label: 'Atendimento', sort_order: 1 },
                { code: 'salas', label: 'Salas', sort_order: 2 },
                { code: 'alimentacao', label: 'Alimentação', sort_order: 3 },
                { code: 'saidas', label: 'Saídas', sort_order: 4 }
            ]
        });
    }
    if (url.pathname === '/api/health') return json(route, { status: 'ok' });
    if (url.pathname === '/api/pdr/config') return json(route, {});
    if (url.pathname === '/api/checkpoints/resolve') {
        return json(route, { checkpoint: MOCK_NODES[0] });
    }
    return json(route, { detail: 'not found' }, 404);
}

export async function installApiMocks(page) {
    await page.route('http://127.0.0.1:8000/**', handleApi);
    await page.route('https://api.pov-unimar.com/**', handleApi);
}

export function seriousViolations(results) {
    return (results.violations || []).filter((item) => item.impact === 'serious' || item.impact === 'critical');
}

export function formatViolations(list) {
    return list.map((item) => {
        const targets = (item.nodes || []).slice(0, 4).map((node) => (node.target || []).join(' ')).join(' | ');
        return `${item.impact} ${item.id}: ${item.help} [${targets}]`;
    }).join('\n');
}
