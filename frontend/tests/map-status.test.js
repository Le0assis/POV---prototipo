import assert from 'node:assert/strict';
import { test } from 'vitest';

import { floorNotice } from '../src/map/map-status.ts';

test('planta ausente é aviso, sem tentativa', () => {
    const notice = floorNotice({ config: null, problems: [] }, '');
    assert.equal(notice.error, false);
    assert.equal(notice.retry, false);
    assert.match(notice.message, /planta/i);
});

test('falha de carga pede para tentar de novo', () => {
    const notice = floorNotice({
        config: { plan_image: 'planta.png' },
        problems: ['Falha ao carregar as conexões.']
    }, '');
    assert.equal(notice.error, true);
    assert.equal(notice.retry, true);
    assert.match(notice.message, /conexões/);
});

test('erro da imagem entra junto com as falhas da API', () => {
    const notice = floorNotice({ problems: ['Falha ao carregar o mapa.'] }, 'Não foi possível carregar a planta.');
    assert.equal(notice.error, true);
    assert.match(notice.message, /planta/);
    assert.match(notice.message, /mapa/);
});

test('a mesma falha repetida aparece uma vez', () => {
    const notice = floorNotice({
        problems: [
            'Falha de conexão com o servidor.',
            'Falha de conexão com o servidor.'
        ]
    }, 'Falha de conexão com o servidor.');
    assert.equal(notice.message, 'Falha de conexão com o servidor.');
});

test('mapa com planta não mostra aviso', () => {
    const notice = floorNotice({ config: { plan_image: 'planta.png' }, problems: [] }, '');
    assert.equal(notice.message, '');
    assert.equal(notice.retry, false);
});
