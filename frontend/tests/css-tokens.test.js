import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'vitest';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const cssDir = path.join(frontendRoot, 'css');

function stripComments(css) {
    return css.replace(/\/\*[\s\S]*?\*\//g, '');
}

function definedVars(css) {
    const found = new Set();
    const re = /(--[A-Za-z0-9_-]+)\s*:/g;
    let match;
    while ((match = re.exec(css))) found.add(match[1]);
    return found;
}

function usedVars(css) {
    const found = new Set();
    const re = /var\(\s*(--[A-Za-z0-9_-]+)/g;
    let match;
    while ((match = re.exec(css))) found.add(match[1]);
    return found;
}

const required = {
    '--bg': '#F7F9FC',
    '--surface': '#FFFFFF',
    '--border': '#E3E8EF',
    '--text': '#1B2433',
    '--text-muted': '#5B6B80',
    '--primary': '#2563EB',
    '--primary-soft': '#DBEAFE',
    '--accent': '#14B8A6',
    '--success': '#14B8A6',
    '--warning': '#F59E0B',
    '--danger': '#DC2626',
    '--you-marker': '#2563EB',
    '--you-halo': '#93C5FD',
    '--space-4': '4px',
    '--space-8': '8px',
    '--space-12': '12px',
    '--space-16': '16px',
    '--space-24': '24px',
    '--space-32': '32px',
    '--radius': '12px'
};

test('tokens.css declara a paleta, a escala e o raio', () => {
    const tokens = stripComments(readFileSync(path.join(cssDir, 'tokens.css'), 'utf8'));
    const values = new Map();
    const re = /(--[A-Za-z0-9_-]+)\s*:\s*([^;]+);/g;
    let match;
    while ((match = re.exec(tokens))) values.set(match[1], match[2].trim());

    Object.entries(required).forEach(([name, value]) => {
        assert.equal(values.has(name), true, `falta ${name}`);
        assert.equal(values.get(name).toLowerCase(), value.toLowerCase(), name);
    });
    assert.equal(values.has('--shadow'), true, 'falta --shadow');
    assert.equal(values.has('--shadow-soft'), true, 'falta --shadow-soft');
    assert.match(values.get('--shadow'), /rgba?\(/);
    assert.match(values.get('--shadow-soft'), /rgba?\(/);
});

test('toda var(--x) usada no CSS existe em tokens.css', () => {
    const tokens = stripComments(readFileSync(path.join(cssDir, 'tokens.css'), 'utf8'));
    const defined = definedVars(tokens);
    const files = readdirSync(cssDir).filter((name) => name.endsWith('.css'));
    const missing = [];

    files.forEach((file) => {
        const text = stripComments(readFileSync(path.join(cssDir, file), 'utf8'));
        usedVars(text).forEach((name) => {
            if (!defined.has(name)) missing.push(`${file}: ${name}`);
        });
    });

    assert.deepEqual(missing, []);
});

test('as páginas do mapa ligam tokens, base e components', () => {
    const pages = [
        ['viewer.html', ''],
        ['locate.html', ''],
        ['admin/editor.html', '../'],
        ['admin/recorder.html', '../']
    ];
    pages.forEach(([page, prefix]) => {
        const html = readFileSync(path.join(frontendRoot, page), 'utf8');
        ['css/tokens.css', 'css/base.css', 'css/components.css'].forEach((href) => {
            assert.equal(html.includes(`href="${prefix}${href}"`), true, `${page} não liga ${prefix}${href}`);
        });
    });
});
