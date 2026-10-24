import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'vitest';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const entries = ['src/pages/locate.ts', 'src/pages/viewer.ts'];
const pages = ['locate.html', 'viewer.html'];

const forbidden = [
    'ensureEditorPassword',
    'editorWrite',
    'setEditorPassword',
    'getEditorPassword',
    'clearEditorPassword',
    'api.reset',
    '/api/reset',
    'saveCheckpoint',
    'saveEdge',
    'processRaw',
    'deleteRoute',
    'createRoute',
    'updateCheckpointPosition',
    'saveMapConfig'
];

const publicApi = new Set([
    'getMap',
    'getMapConfig',
    'getConnections',
    'getPdrConfig',
    'getRoutes',
    'getRoute',
    'getCompassRoute',
    'localize',
    'currentLocation',
    'ping'
]);

function resolveImport(fromFile, spec) {
    if (!spec.startsWith('.')) return null;
    const base = path.normalize(path.join(path.dirname(fromFile), spec)).split(path.sep).join('/');
    const candidates = [];
    if (base.endsWith('.js')) {
        candidates.push(`${base.slice(0, -3)}.ts`, `${base.slice(0, -3)}.tsx`, base);
    } else if (base.endsWith('.jsx')) {
        candidates.push(`${base.slice(0, -4)}.tsx`, `${base.slice(0, -4)}.ts`, base);
    } else if (base.endsWith('.ts') || base.endsWith('.tsx')) {
        candidates.push(base);
    } else {
        candidates.push(`${base}.ts`, `${base}.tsx`, `${base}.js`);
    }
    return candidates.find((rel) => existsSync(path.join(frontendRoot, rel))) || null;
}

function collect(entry) {
    const seen = new Set();
    const files = [];
    const queue = [entry];
    while (queue.length) {
        const rel = queue.pop();
        if (seen.has(rel)) continue;
        seen.add(rel);
        const text = readFileSync(path.join(frontendRoot, rel), 'utf8');
        files.push({ rel, text });
        const re = /from\s+['"](\.[^'"]+)['"]/g;
        let match;
        while ((match = re.exec(text))) {
            const next = resolveImport(rel, match[1]);
            if (next) queue.push(next);
        }
    }
    return files;
}

function importedApiNames(text) {
    const names = [];
    const re = /import\s*\{([^}]+)\}\s*from\s*['"][^'"]*\/api\.js['"]/g;
    let match;
    while ((match = re.exec(text))) {
        match[1].split(',').forEach((part) => {
            const name = part.trim().split(/\s+as\s+/)[0].trim();
            if (name) names.push(name);
        });
    }
    return names;
}

test('locate e viewer não importam reset nem a senha do editor', () => {
    const files = [];
    entries.forEach((entry) => files.push(...collect(entry)));
    pages.forEach((page) => {
        files.push({
            rel: page,
            text: readFileSync(path.join(frontendRoot, page), 'utf8')
        });
    });

    const seen = new Set();
    files.forEach(({ rel, text }) => {
        if (seen.has(rel)) return;
        seen.add(rel);
        if (rel.endsWith('src/core/api.ts')) return;

        forbidden.forEach((token) => {
            assert.equal(text.includes(token), false, `${rel} contém ${token}`);
        });
        assert.equal(/import\s+\*\s+as\s+\w+\s+from\s+['"][^'"]*\/api\.js['"]/.test(text), false,
            `${rel} importa o módulo de API inteiro`);
        assert.equal(/import\s*\{[^}]*\breset\b/.test(text), false, `${rel} importa reset`);

        importedApiNames(text).forEach((name) => {
            assert.equal(publicApi.has(name), true, `${rel} importa ${name}, que não é leitura pública`);
        });
    });
});
