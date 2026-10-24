import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'vitest';

import { MAP_COLOR_TOKENS } from '../src/core/colors.ts';
import {
    adaptCategories,
    adaptCheckpoint,
    adaptCheckpoints,
    adaptResolve,
    checkpointSlug,
    isResolveNotFound
} from '../src/core/checkpoints.ts';

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

    const named = adaptCategories({
        categories: [
            { code: 'alimentacao', name: 'Alimentação', order: 3, icon: 'utensils' }
        ]
    });
    assert.equal(named[0].label, 'Alimentação');
    assert.equal(named[0].sort_order, 3);
    assert.equal(named[0].icon, 'utensils');
    assert.equal(
        adaptCheckpoint({ name: 'Copa', category: { code: 'alimentacao', name: 'Alimentação', icon: 'utensils' } }).category.icon,
        'utensils'
    );

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

    ['src/map/layers.ts', 'src/map/path-preview.ts', 'src/pages/recorder.ts'].forEach((rel) => {
        const text = readFileSync(path.join(frontendRoot, rel), 'utf8');
        assert.equal(/#[0-9a-fA-F]{3,8}\b/.test(text), false, rel);
        assert.equal(/rgba?\(/.test(text), false, rel);
    });

    const routeBar = readFileSync(path.join(frontendRoot, 'src/ui/route-bar.ts'), 'utf8');
    assert.equal(routeBar.includes("createElement('input'"), false);
    assert.equal(routeBar.includes('Leia um QR para saber onde você está'), true);
    assert.equal(routeBar.includes('Iniciar rota'), true);

    const index = readFileSync(path.join(frontendRoot, 'index.html'), 'utf8');
    const main = readFileSync(path.join(frontendRoot, 'src/main.tsx'), 'utf8');
    assert.match(index, /\/src\/main\.tsx/);
    assert.match(main, /['"]\.\/boot['"]/);
    assert.match(main, /['"]\.\/app['"]/);
    assert.match(index, /aria-live="polite"/);
    assert.match(index, /Para onde você quer ir\?/);
    assert.doesNotMatch(index, /href="editor\.html"/);
    assert.doesNotMatch(index, /href="recorder\.html"/);
    const viewer = readFileSync(path.join(frontendRoot, 'viewer.html'), 'utf8');
    assert.match(viewer, /Mapa do prédio/);
});
