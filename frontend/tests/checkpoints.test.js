import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import { MAP_COLOR_TOKENS } from '../js/core/colors.js';
import {
    adaptCategories,
    adaptCheckpoint,
    adaptCheckpoints,
    adaptResolve,
    checkpointSlug,
    isResolveNotFound
} from '../js/core/checkpoints.js';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

test('usa o slug e, sem ele, o nome', () => {
    const withSlug = adaptCheckpoint({
        name: 'Recepção',
        id: 'Recepção',
        slug: 'recepcao',
        building_id: 1,
        category: { code: 'atendimento', label: 'Atendimento' },
        pos_x_px: 3,
        anchor: { pos_x_px: 3, pos_y_px: 4 }
    });
    assert.equal(withSlug.slug, 'recepcao');
    assert.equal(withSlug.name, 'Recepção');
    assert.equal(withSlug.building_id, 1);
    assert.deepEqual(withSlug.category, { code: 'atendimento', label: 'Atendimento' });
    assert.deepEqual(withSlug.anchor, { pos_x_px: 3, pos_y_px: 4 });

    assert.equal(checkpointSlug({ name: 'Sala', slug: '  ' }), 'Sala');
    assert.equal(adaptCheckpoint({ slug: null, name: 'Sala' }).slug, 'Sala');
    assert.equal(adaptCheckpoint({ id: 'Porta' }).slug, 'Porta');
    assert.equal(adaptCheckpoint({ label: 'Hall' }).name, 'Hall');
    assert.equal(adaptCheckpoint({ slug: 'only' }).name, 'only');
    assert.equal(adaptCheckpoint(null), null);
    assert.equal(adaptCheckpoint({ category: 'banheiros' }), null);
    assert.equal(adaptCheckpoint({ name: 'Copa', category: 'banheiros' }).category.code, 'banheiros');
    assert.equal(adaptCheckpoint({ name: 'Copa', building_id: 'x' }).building_id, null);
    assert.equal(adaptCheckpoint({ name: 'Copa', building_id: 0 }).building_id, 0);
});

test('lista, categorias e o resolve público', () => {
    const list = adaptCheckpoints([
        { name: 'A', slug: 'a' },
        null,
        { id: '' },
        { name: 'Sem slug' }
    ]);
    assert.deepEqual(list.map((item) => item.slug), ['a', 'Sem slug']);

    const wrapped = adaptCategories({
        status: 'success',
        categories: [
            { code: 'atendimento', label: 'Atendimento', sort_order: 1 },
            { code: '', label: 'inválida' },
            { code: 'saidas', sort_order: 'nope' }
        ]
    });
    assert.deepEqual(wrapped, [
        { code: 'atendimento', label: 'Atendimento', sort_order: 1 },
        { code: 'saidas', label: 'saidas', sort_order: null }
    ]);
    assert.equal(adaptCategories([{ code: 'hall', label: 'Hall', sort_order: 3 }])[0].code, 'hall');

    const resolved = adaptResolve({
        status: 'success',
        checkpoint: {
            name: 'Recepção',
            slug: 'recepcao',
            building_id: 1,
            category: { code: 'atendimento', label: 'Atendimento' }
        }
    });
    assert.equal(resolved.slug, 'recepcao');
    assert.equal(adaptResolve({ name: 'Sala' }).slug, 'Sala');
    assert.equal(adaptResolve(null), null);
    assert.equal(isResolveNotFound({ status: 404 }), true);
    assert.equal(isResolveNotFound({ status: 500 }), false);
    assert.equal(isResolveNotFound(null), false);
});

test('polilinha, marcador e sparkline leem token em vez de cor solta', () => {
    const tokens = readFileSync(path.join(frontendRoot, 'css/tokens.css'), 'utf8');
    Object.values(MAP_COLOR_TOKENS).forEach(([name]) => {
        assert.match(tokens, new RegExp(`${name}\\s*:`), name);
    });

    ['js/map/layers.js', 'js/map/path-preview.js', 'js/pages/recorder.js'].forEach((rel) => {
        const text = readFileSync(path.join(frontendRoot, rel), 'utf8');
        assert.equal(/#[0-9a-fA-F]{3,8}\b/.test(text), false, rel);
        assert.equal(/rgba?\(/.test(text), false, rel);
    });

    const routeBar = readFileSync(path.join(frontendRoot, 'js/ui/route-bar.js'), 'utf8');
    assert.equal(routeBar.includes("createElement('input'"), false);
    assert.equal(routeBar.includes('Leia um QR para saber onde você está'), true);
    assert.equal(routeBar.includes('Iniciar rota'), true);

    const index = readFileSync(path.join(frontendRoot, 'index.html'), 'utf8');
    assert.match(index, /js\/boot\.js/);
    assert.match(index, /js\/app\.js/);
    assert.match(index, /aria-live="polite"/);
    assert.match(index, /Para onde você quer ir\?/);
    assert.doesNotMatch(index, /href="editor\.html"/);
    assert.doesNotMatch(index, /href="recorder\.html"/);
    const viewer = readFileSync(path.join(frontendRoot, 'viewer.html'), 'utf8');
    assert.match(viewer, /Mapa do prédio/);
});
