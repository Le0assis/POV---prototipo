import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'vitest';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const image = 'https://pov-unimar.com/og.png';
const alt = 'POV, mapa do prédio com a rota em azul e o destino em âmbar.';

const pages = [
    ['index.html', 'POV — mapa do prédio', 'https://pov-unimar.com/', 'Busque uma sala no prédio'],
    ['viewer.html', 'POV — Mapa do prédio', 'https://pov-unimar.com/viewer.html', 'só de leitura'],
    ['locate.html', 'POV — Navegar', 'https://pov-unimar.com/locate.html', 'aresta calibrada'],
    ['admin/index.html', 'POV — Administração', 'https://pov-unimar.com/admin/', 'Ferramentas do mapa'],
    ['admin/editor.html', 'POV — Editor', 'https://pov-unimar.com/admin/editor.html', 'posição de cada ponto'],
    ['admin/recorder.html', 'POV — Gravador', 'https://pov-unimar.com/admin/recorder.html', 'caminhada entre dois checkpoints'],
    ['admin/map-config.html', 'POV — Configurar planta', 'https://pov-unimar.com/admin/map-config.html', 'pixels por metro'],
    ['admin/qrcodes.html', 'POV — Gerar QR codes', 'https://pov-unimar.com/admin/qrcodes.html', 'QR code de cada checkpoint']
];

function attr(html, tag, name) {
    const re = new RegExp(`<${tag}\\b[^>]*\\b(?:name|property)="${name}"[^>]*content="([^"]*)"`, 'i');
    const match = html.match(re);
    return match ? match[1] : '';
}

test('cada página HTML tem description, Open Graph e Twitter card', () => {
    const found = [];
    const walk = (dir) => {
        for (const entry of readdirSync(dir, { withFileTypes: true })) {
            if (entry.name === 'vendor' || entry.name === 'dist' || entry.name === 'node_modules') continue;
            const full = path.join(dir, entry.name);
            if (entry.isDirectory()) walk(full);
            else if (entry.name.endsWith('.html')) found.push(path.relative(frontendRoot, full));
        }
    };
    walk(frontendRoot);
    assert.deepEqual(found.sort(), pages.map(([file]) => file).sort());

    pages.forEach(([file, title, url, snippet]) => {
        const html = readFileSync(path.join(frontendRoot, file), 'utf8');
        assert.match(html, new RegExp(`<title>${title}</title>`), file);
        assert.equal(attr(html, 'meta', 'description').includes(snippet), true, file);
        assert.equal(attr(html, 'meta', 'og:title'), title, file);
        assert.equal(attr(html, 'meta', 'og:description'), attr(html, 'meta', 'description'), file);
        assert.equal(attr(html, 'meta', 'og:url'), url, file);
        assert.equal(attr(html, 'meta', 'og:image'), image, file);
        assert.equal(attr(html, 'meta', 'og:image:alt'), alt, file);
        assert.equal(attr(html, 'meta', 'twitter:card'), 'summary_large_image', file);
        assert.equal(attr(html, 'meta', 'twitter:title'), title, file);
        assert.equal(attr(html, 'meta', 'twitter:description'), attr(html, 'meta', 'description'), file);
        assert.equal(attr(html, 'meta', 'twitter:url'), url, file);
        assert.equal(attr(html, 'meta', 'twitter:image'), image, file);
        assert.match(html, new RegExp(`<link rel="canonical" href="${url}">`), file);
        assert.equal(html.includes('/api/localize'), false, file);
    });
});

test('a imagem de compartilhamento é um PNG 1200×630 da identidade atual', () => {
    const file = path.join(frontendRoot, 'public/og.png');
    const bytes = readFileSync(file);
    assert.equal(bytes.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
    assert.equal(bytes.readUInt32BE(16), 1200);
    assert.equal(bytes.readUInt32BE(20), 630);
    const svg = readFileSync(path.join(frontendRoot, 'public/og.svg'), 'utf8');
    ['#F7F9FC', '#2563EB', '#14B8A6', '#F59E0B', '#1B2433'].forEach((color) => {
        assert.equal(svg.includes(color), true, color);
    });
    const dist = path.join(frontendRoot, 'dist/og.png');
    assert.equal(statSync(dist).isFile(), true);
    assert.equal(readFileSync(dist).equals(bytes), true);
});
