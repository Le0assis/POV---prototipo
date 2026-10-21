import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import { A11Y_STORAGE_KEY, applyA11yClasses, readA11yPrefs, saveA11yPrefs } from '../js/a11y/prefs.js';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function memoryStorage(initial) {
    const bag = new Map(initial || []);
    return {
        getItem(key) {
            return bag.has(key) ? bag.get(key) : null;
        },
        setItem(key, value) {
            bag.set(key, String(value));
        }
    };
}

function fakeRoot() {
    const classes = new Set();
    return {
        classList: {
            toggle(name, on) {
                if (on) classes.add(name);
                else classes.delete(name);
                return classes.has(name);
            },
            contains(name) {
                return classes.has(name);
            }
        }
    };
}

test('salva alto contraste e fonte grande e aplica as classes', () => {
    const storage = memoryStorage();
    assert.deepEqual(readA11yPrefs(storage), { hc: false, fontLg: false, speech: false });
    const saved = saveA11yPrefs({ hc: true, fontLg: true, speech: false }, storage);
    assert.deepEqual(saved, { hc: true, fontLg: true, speech: false });
    assert.equal(storage.getItem(A11Y_STORAGE_KEY), JSON.stringify(saved));
    assert.deepEqual(readA11yPrefs(storage), saved);

    const root = fakeRoot();
    applyA11yClasses(root, readA11yPrefs(storage));
    assert.equal(root.classList.contains('hc'), true);
    assert.equal(root.classList.contains('font-lg'), true);

    applyA11yClasses(root, saveA11yPrefs({ hc: false, fontLg: false, speech: true }, storage));
    assert.equal(root.classList.contains('hc'), false);
    assert.equal(root.classList.contains('font-lg'), false);
    assert.equal(readA11yPrefs(storage).speech, true);
});

test('JSON inválido não liga preferência nenhuma', () => {
    const storage = memoryStorage([[A11Y_STORAGE_KEY, '{']]);
    assert.deepEqual(readA11yPrefs(storage), { hc: false, fontLg: false, speech: false });
});

test('o script do head aplica hc e font-lg antes da folha de estilo', () => {
    const pages = [
        'index.html',
        'admin/index.html',
        'admin/editor.html',
        'admin/recorder.html',
        'admin/map-config.html',
        'admin/qrcodes.html'
    ];
    pages.forEach((page) => {
        const html = readFileSync(path.join(frontendRoot, page), 'utf8');
        const scriptAt = html.indexOf(`localStorage.getItem('${A11Y_STORAGE_KEY}')`);
        const styleAt = html.indexOf('rel="stylesheet"');
        assert.equal(scriptAt > 0, true, page);
        assert.equal(styleAt > scriptAt, true, page);
        assert.match(html, /classList\.add\('hc'\)/, page);
        assert.match(html, /classList\.add\('font-lg'\)/, page);
    });
    const menu = readFileSync(path.join(frontendRoot, 'admin/index.html'), 'utf8');
    assert.match(menu, /href="qrcodes\.html"/);
    assert.doesNotMatch(menu, /em breve/);
    const page = readFileSync(path.join(frontendRoot, 'admin/qrcodes.html'), 'utf8');
    assert.match(page, /Imprimir \/ Salvar PDF/);
    assert.match(page, /id="admin-header"/);
    assert.match(page, /\.\.\/js\/boot\.js/);
});
