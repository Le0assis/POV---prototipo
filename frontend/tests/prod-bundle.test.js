import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'vitest';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dist = path.join(frontendRoot, 'dist');

const forbidden = ['/api/localize', '/api/current_location', '/api/reset'];

function walk(dir, acc = []) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) walk(full, acc);
        else if (/\.(js|html|css)$/.test(entry.name)) acc.push(full);
    }
    return acc;
}

test('o build de produção não contém a localização fixa e aponta para a API', () => {
    assert.equal(statSync(dist).isDirectory(), true, 'frontend/dist ausente; rode npm run build');
    const files = walk(dist);
    assert.ok(files.some((file) => file.endsWith('.js')), 'o dist não tem JavaScript');
    const js = files.filter((file) => file.endsWith('.js'));
    const bundle = js.map((file) => readFileSync(file, 'utf8')).join('\n');
    forbidden.forEach((token) => {
        assert.equal(bundle.includes(token), false, `o bundle contém ${token}`);
    });
    files.filter((file) => file.endsWith('.html')).forEach((file) => {
        const text = readFileSync(file, 'utf8');
        forbidden.forEach((token) => {
            assert.equal(text.includes(token), false, `${file} contém ${token}`);
        });
    });
    assert.equal(bundle.includes('https://api.pov-unimar.com'), true);
});
