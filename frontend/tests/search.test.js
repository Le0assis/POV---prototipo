import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'vitest';

import { loadDestinationCatalog } from '../src/core/destination-catalog.ts';
import {
    ALL_CHIP,
    OUTROS_LABEL,
    SEARCH_DEBOUNCE_MS,
    buildDestinationCatalog,
    debounce,
    destinationCountLabel,
    foldText,
    formatDistanceMeters,
    searchDestinations,
    straightLineMeters
} from '../src/core/search.ts';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const categories = [
    { code: 'atendimento', label: 'Atendimento', sort_order: 1, icon: 'concierge-bell' },
    { code: 'banheiros', label: 'Banheiros', sort_order: 2, icon: 'bath' },
    { code: 'alimentacao', name: 'Alimentação', order: 3, icon: 'utensils' },
    { code: 'saidas', label: 'Saídas', sort_order: 4, icon: 'door-open' }
];

function place(partial) {
    return {
        categoryCode: 'atendimento',
        categoryName: 'Atendimento',
        icon: '',
        pos_x_px: null,
        pos_y_px: null,
        ...partial
    };
}

test('a busca ignora acento e maiúsculas no nome e na categoria', () => {
    const items = [
        place({ slug: 'agua', name: 'Água', categoryCode: 'banheiros', categoryName: 'Banheiros' }),
        place({ slug: 'sala', name: 'Sala de reunião', categoryCode: 'atendimento', categoryName: 'Atendimento' }),
        place({ slug: 'porta', name: 'Porta', categoryCode: 'saidas', categoryName: 'Saídas' })
    ];

    assert.equal(foldText('Água'), 'agua');
    assert.deepEqual(searchDestinations(items, { query: 'AGUA' }).map((item) => item.slug), ['agua']);
    assert.deepEqual(searchDestinations(items, { query: 'reuniao' }).map((item) => item.slug), ['sala']);
    assert.deepEqual(searchDestinations(items, { query: 'SAIDAS' }).map((item) => item.slug), ['porta']);
    assert.deepEqual(searchDestinations(items, { query: 'aliment' }), []);
    assert.deepEqual(
        searchDestinations(
            [place({ slug: 'copa', name: 'Copa', categoryCode: 'alimentacao', categoryName: 'Alimentação' })],
            { query: 'alimentacao' }
        ).map((item) => item.slug),
        ['copa']
    );
});

test('relevância coloca quem começa com o texto antes de quem só contém', () => {
    const items = [
        place({ slug: 'area', name: 'Área de recreação' }),
        place({ slug: 'rec', name: 'Recreação' }),
        place({ slug: 'recep', name: 'Recepção' }),
        place({ slug: 'copa', name: 'Copa' })
    ];
    assert.deepEqual(
        searchDestinations(items, { query: 'rec' }).map((item) => item.slug),
        ['recep', 'rec', 'area']
    );
});

test('o chip combina com o texto e a ordem sem texto é pt-BR', () => {
    const items = [
        place({ slug: 'zebra', name: 'Zebra', categoryCode: 'atendimento', categoryName: 'Atendimento' }),
        place({ slug: 'agua', name: 'Água', categoryCode: 'banheiros', categoryName: 'Banheiros' }),
        place({ slug: 'acao', name: 'ação', categoryCode: 'banheiros', categoryName: 'Banheiros' }),
        place({ slug: 'abacate', name: 'abacate', categoryCode: 'alimentacao', categoryName: 'Alimentação' }),
        place({ slug: 'norte', name: 'Banheiro norte', categoryCode: 'banheiros', categoryName: 'Banheiros' })
    ];

    assert.deepEqual(
        searchDestinations(items).map((item) => item.name),
        ['abacate', 'ação', 'Água', 'Banheiro norte', 'Zebra']
    );
    assert.deepEqual(
        searchDestinations(items, { chip: 'banheiros' }).map((item) => item.slug),
        ['acao', 'agua', 'norte']
    );
    assert.deepEqual(
        searchDestinations(items, { chip: 'banheiros', query: 'norte' }).map((item) => item.slug),
        ['norte']
    );
    assert.deepEqual(searchDestinations(items, { chip: 'saidas', query: 'ban' }), []);
    assert.equal(ALL_CHIP, 'todos');
});

test('com origem a distância entra na ordenação só quando não há texto', () => {
    const items = [
        place({ slug: 'origin', name: 'Origem', pos_x_px: 0, pos_y_px: 0 }),
        place({ slug: 'dado', name: 'Dado', pos_x_px: 10, pos_y_px: 0 }),
        place({ slug: 'casa', name: 'Casa', pos_x_px: 100, pos_y_px: 0 }),
        place({ slug: 'sem', name: 'Sem ponto', categoryCode: 'banheiros', categoryName: 'Banheiros' })
    ];

    const idle = searchDestinations(items, { originSlug: 'origin', pxPerM: 10 });
    assert.deepEqual(idle.map((item) => item.slug), ['dado', 'casa', 'sem']);
    assert.equal(idle[0].distanceLabel, '~1 m');
    assert.equal(idle[1].distanceLabel, '~10 m');
    assert.equal(idle[2].distanceLabel, '');
    assert.equal(idle.some((item) => item.slug === 'origin'), false);

    const typed = searchDestinations(items, { query: 'a', originSlug: 'origin', pxPerM: 10 });
    assert.deepEqual(typed.map((item) => item.slug), ['casa', 'dado', 'sem']);
    assert.equal(typed.find((item) => item.slug === 'dado').distanceLabel, '~1 m');

    const noScale = searchDestinations(items, { originSlug: 'origin' });
    assert.equal(noScale.every((item) => item.distanceLabel === ''), true);
    assert.deepEqual(noScale.map((item) => item.slug), ['casa', 'dado', 'sem']);
});

test('a distância é a reta em metros e o rótulo arredonda', () => {
    assert.equal(straightLineMeters({ pos_x_px: 0, pos_y_px: 0 }, { pos_x_px: 30, pos_y_px: 40 }, 10), 5);
    assert.equal(formatDistanceMeters(12), '~12 m');
    assert.equal(formatDistanceMeters(12.4), '~12 m');
    assert.equal(straightLineMeters({ pos_x_px: 0, pos_y_px: 0 }, { pos_x_px: 120, pos_y_px: 0 }, 10), 12);
    assert.equal(straightLineMeters({ pos_x_px: 0, pos_y_px: 0 }, { pos_x_px: 1, pos_y_px: 1 }, null), null);
    assert.equal(straightLineMeters({ pos_x_px: 0, pos_y_px: 0 }, { pos_x_px: 1, pos_y_px: 1 }, 0), null);
    assert.equal(straightLineMeters({ pos_x_px: 0, pos_y_px: 0 }, { pos_x_px: null, pos_y_px: 1 }, 10), null);
    assert.equal(destinationCountLabel(0), '0 destinos');
    assert.equal(destinationCountLabel(1), '1 destino');
    assert.equal(destinationCountLabel(12), '12 destinos');
});

test('sem categorias os chips somem e tudo fica em Outros', () => {
    const checkpoints = [
        { slug: 'recepcao', name: 'Recepção', category: { code: 'atendimento', label: 'Atendimento' }, pos_x_px: 3, pos_y_px: 4 },
        { slug: 'copa', name: 'Copa', category: null },
        { slug: 'porta', name: 'Porta' }
    ];

    const missing = buildDestinationCatalog(checkpoints, null);
    assert.equal(missing.showChips, false);
    assert.deepEqual(missing.categories, []);
    assert.equal(missing.items.every((item) => item.categoryName === OUTROS_LABEL), true);
    assert.equal(missing.items.every((item) => item.categoryCode === 'outros'), true);
    assert.equal(buildDestinationCatalog(checkpoints, []).showChips, false);
    assert.deepEqual(
        searchDestinations(missing.items, { query: 'outros' }).map((item) => item.slug),
        ['copa', 'porta', 'recepcao']
    );

    const known = buildDestinationCatalog(checkpoints, categories);
    assert.equal(known.showChips, true);
    assert.deepEqual(known.categories.map((item) => item.code), ['atendimento', 'banheiros', 'alimentacao', 'saidas']);
    assert.equal(known.categories[2].name, 'Alimentação');
    assert.equal(known.categories[2].icon, 'utensils');
    const bySlug = new Map(known.items.map((item) => [item.slug, item]));
    assert.equal(bySlug.get('recepcao').categoryName, 'Atendimento');
    assert.equal(bySlug.get('recepcao').icon, 'concierge-bell');
    assert.equal(bySlug.get('recepcao').pos_x_px, 3);
    assert.equal(bySlug.get('copa').categoryName, OUTROS_LABEL);
    assert.equal(bySlug.get('porta').categoryName, OUTROS_LABEL);
    assert.equal(
        buildDestinationCatalog(
            [{ slug: 'x', name: 'Hall', category: 'desconhecida' }],
            categories
        ).items[0].categoryName,
        OUTROS_LABEL
    );
});

test('404 de categorias não quebra a lista e a planta ausente só tira a escala', async () => {
    const notFound = Object.assign(new Error('não encontrado'), { status: 404 });
    const catalog = await loadDestinationCatalog({
        getMap: async () => ({
            nodes: [
                { name: 'Copa', slug: 'copa', pos_x_px: 30, pos_y_px: 40, category: { code: 'alimentacao', label: 'Alimentação' } },
                { name: 'Recepção', slug: 'recepcao', pos_x_px: 0, pos_y_px: 0 }
            ]
        }),
        getCategories: async () => {
            throw notFound;
        },
        getMapConfig: async () => ({ map_config: { plan_image: '', px_per_m: 10, rotation_rad: 0 } })
    });
    const built = buildDestinationCatalog(catalog.checkpoints, catalog.categories);
    assert.equal(catalog.categories, null);
    assert.equal(catalog.pxPerM, 10);
    assert.equal(built.showChips, false);
    assert.equal(built.items.every((item) => item.categoryName === OUTROS_LABEL), true);
    const distances = searchDestinations(built.items, { originSlug: 'recepcao', pxPerM: catalog.pxPerM });
    assert.deepEqual(distances.map((item) => item.slug), ['copa']);
    assert.equal(distances[0].distanceLabel, '~5 m');

    const noPlan = await loadDestinationCatalog({
        getMap: async () => ({ nodes: [{ name: 'Copa', slug: 'copa' }] }),
        getCategories: async () => ({ categories }),
        getMapConfig: async () => {
            throw new Error('sem planta');
        }
    });
    assert.equal(noPlan.pxPerM, null);
    assert.equal(buildDestinationCatalog(noPlan.checkpoints, noPlan.categories).showChips, true);

    await assert.rejects(
        () => loadDestinationCatalog({
            getMap: async () => {
                throw Object.assign(new Error('offline'), { status: 0 });
            },
            getCategories: async () => ({ categories: [] }),
            getMapConfig: async () => ({})
        }),
        /destinos/
    );
});

test('o texto da busca espera 100ms', async () => {
    assert.equal(SEARCH_DEBOUNCE_MS, 100);
    let calls = 0;
    const run = debounce(() => {
        calls += 1;
    });
    run();
    run();
    assert.equal(calls, 0);
    await new Promise((resolve) => setTimeout(resolve, 80));
    assert.equal(calls, 0);
    await new Promise((resolve) => setTimeout(resolve, 40));
    assert.equal(calls, 1);
    run.cancel();
});

test('a folha, a prévia e o mapa expõem o contrato da busca', () => {
    const sheet = readFileSync(path.join(frontendRoot, 'src/ui/search-sheet.ts'), 'utf8');
    const css = readFileSync(path.join(frontendRoot, 'css/visitor.css'), 'utf8');
    const app = readFileSync(path.join(frontendRoot, 'src/app.ts'), 'utf8');
    const index = readFileSync(path.join(frontendRoot, 'index.html'), 'utf8');

    assert.match(sheet, /SEARCH_DEBOUNCE_MS/);
    assert.match(sheet, /role', 'listbox'/);
    assert.match(sheet, /role', 'combobox'/);
    assert.match(sheet, /aria-pressed/);
    assert.match(sheet, /Nenhum destino encontrado/);
    assert.match(sheet, /Limpar busca/);
    assert.match(sheet, /Tentar de novo/);
    assert.match(sheet, /ArrowDown/);
    assert.match(sheet, /search-field/);
    assert.match(sheet, /destination-query/);
    assert.match(css, /90dvh/);
    assert.match(css, /min-height:\s*48px/);
    assert.match(app, /select-destination/);
    assert.match(app, /Leia um QR para saber onde você está/);
    assert.match(app, /highlight/);
    assert.match(index, /readonly/);
    assert.equal(index.includes('id="destination-query"'), false);
    assert.match(index, /id="search-field"/);
});
