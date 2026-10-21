import assert from 'node:assert/strict';
import test from 'node:test';

import {
    RESOLVE_FALLBACK_WARNING,
    RESOLVE_RETRY,
    RESOLVE_UNRECOGNIZED,
    resolveScannedCheckpoint
} from '../js/core/checkpoints.js';

const reception = {
    name: 'Recepção',
    slug: 'recepcao',
    building_id: 1,
    category: { code: 'atendimento', label: 'Atendimento' },
    pos_x_px: 12,
    pos_y_px: 40
};

function jsonResponse(status, body) {
    return {
        ok: status >= 200 && status < 300,
        status,
        json: async () => body
    };
}

async function withFetch(handler, run) {
    const original = globalThis.fetch;
    globalThis.fetch = handler;
    try {
        return await run();
    } finally {
        globalThis.fetch = original;
    }
}

test('200 grava o checkpoint do contrato público', async () => {
    await withFetch(async (url, options) => {
        const href = String(url);
        assert.match(href, /\/api\/checkpoints\/resolve\?/);
        assert.match(href, /b=1/);
        assert.match(href, /cp=recepcao/);
        assert.equal(options.method, 'GET');
        assert.equal(options.headers['X-Editor-Password'], undefined);
        return jsonResponse(200, {
            status: 'success',
            checkpoint: reception
        });
    }, async () => {
        const found = await resolveScannedCheckpoint({ b: 1, cp: 'recepcao' });
        assert.equal(found.slug, 'recepcao');
        assert.equal(found.name, 'Recepção');
        assert.equal(found.building_id, 1);
        assert.equal(found.pos_x_px, 12);
    });
});

test('404 do checkpoint não usa a lista e pede QR não reconhecido', async () => {
    await withFetch(async () => jsonResponse(404, { detail: 'Checkpoint não encontrado.' }), async () => {
        await assert.rejects(
            () => resolveScannedCheckpoint({
                b: 1,
                cp: 'recepcao',
                checkpoints: [reception]
            }),
            (err) => err.code === 'not-found' && err.message === RESOLVE_UNRECOGNIZED
        );
    });
});

test('falha de rede pede Tentar de novo e não inventa origem', async () => {
    await withFetch(async () => {
        throw new TypeError('Failed to fetch');
    }, async () => {
        await assert.rejects(
            () => resolveScannedCheckpoint({
                b: 1,
                cp: 'recepcao',
                checkpoints: [reception]
            }),
            (err) => err.code === 'network' && err.message === RESOLVE_RETRY
        );
    });
});

test('404 da rota e 405 caem na lista já carregada e avisam', async () => {
    const warnings = [];
    await withFetch(async () => jsonResponse(405, { detail: 'Method Not Allowed' }), async () => {
        const found = await resolveScannedCheckpoint({
            b: 1,
            cp: 'recepcao',
            checkpoints: [reception],
            warn: (message) => warnings.push(message)
        });
        assert.equal(found.slug, 'recepcao');
        assert.equal(found.name, 'Recepção');
    });

    await withFetch(async () => jsonResponse(404, { detail: 'Not Found' }), async () => {
        const found = await resolveScannedCheckpoint({
            b: 1,
            cp: 'recepcao',
            checkpoints: [{ name: 'Recepção', slug: 'recepcao', building_id: 1 }],
            warn: (message) => warnings.push(message)
        });
        assert.equal(found.slug, 'recepcao');
    });

    assert.equal(warnings.length, 2);
    assert.equal(warnings.every((message) => message === RESOLVE_FALLBACK_WARNING), true);

    await withFetch(async () => jsonResponse(404, 'nope'), async () => {
        await assert.rejects(
            () => resolveScannedCheckpoint({
                b: 9,
                cp: 'nao-existe',
                checkpoints: [reception],
                warn: () => {}
            }),
            (err) => err.code === 'not-found'
        );
    });
});

test('slug sem prédio procura na lista, sem chamar o resolve', async () => {
    let called = 0;
    await withFetch(async () => {
        called += 1;
        return jsonResponse(500, {});
    }, async () => {
        const found = await resolveScannedCheckpoint({
            cp: 'recepcao',
            checkpoints: [reception]
        });
        assert.equal(found.name, 'Recepção');
        assert.equal(called, 0);
    });
});
