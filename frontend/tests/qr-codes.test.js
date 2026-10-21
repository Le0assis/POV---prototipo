import assert from 'node:assert/strict';
import test from 'node:test';

import { buildQr, parseQr } from '../js/qr/qr-format.js';
import { MISSING_SLUG_WARNING, filterQrCheckpoints, qrCheckpoints, qrJobs } from '../js/qr/qr-batch.js';
import { QR_ERROR_CORRECTION, qrSvg } from '../js/qr/qr-draw.js';

const rows = [
    {
        name: 'Recepção',
        slug: 'recepcao',
        building_id: 1,
        category: { code: 'atendimento', label: 'Atendimento' }
    },
    {
        name: 'Sala de aula',
        slug: 'sala',
        building_id: 2,
        category: { code: 'salas', label: 'Salas' }
    },
    {
        name: 'Pátio',
        slug: '   ',
        building_id: 1,
        category: { code: 'saidas', label: 'Saídas' }
    },
    { name: 'Copa', building_id: 1, category: { code: 'alimentacao', label: 'Alimentação' } }
];

test('o conteúdo do QR é o buildQr e o parser devolve o mesmo cp e b', () => {
    const prepared = qrCheckpoints(rows);
    const { jobs } = qrJobs(prepared.filter((row) => row.slug === 'recepcao' || row.slug === 'sala'));
    assert.equal(jobs.length, 2);
    jobs.forEach((job) => {
        assert.equal(job.text, buildQr({ cp: job.slug, b: job.building_id }));
        assert.deepEqual(parseQr(job.text), {
            cp: job.slug,
            b: job.building_id,
            v: 1
        });
    });
    assert.equal(QR_ERROR_CORRECTION, 'M');
    const svg = qrSvg(jobs[0].text, { title: 'QR code de Recepção', titleId: 'qr-title-0' });
    assert.match(svg, /<svg/);
    assert.match(svg, /id="qr-title-0"/);
    assert.notEqual(qrSvg(jobs[0].text), qrSvg(jobs[1].text));
});

test('checkpoint sem slug é pulado com o aviso', () => {
    const prepared = qrCheckpoints(rows);
    const patio = prepared.find((row) => row.name === 'Pátio');
    const copa = prepared.find((row) => row.name === 'Copa');
    assert.equal(patio.missingSlug, true);
    assert.equal(patio.slug, '');
    assert.equal(copa.missingSlug, true);
    assert.equal(copa.name, 'Copa');
    assert.equal(copa.categoryLabel, 'Alimentação');

    const { jobs, skipped } = qrJobs(prepared);
    assert.deepEqual(jobs.map((job) => job.slug), ['recepcao', 'sala']);
    assert.equal(skipped.length, 2);
    skipped.forEach((row) => {
        assert.equal(row.warning, MISSING_SLUG_WARNING);
        assert.equal(row.missingSlug, true);
    });
    assert.equal(qrCheckpoints([{}, null, { slug: '' }]).length, 0);
});

test('o filtro casa nome e categoria', () => {
    const prepared = qrCheckpoints(rows);
    assert.deepEqual(filterQrCheckpoints(prepared, 'aula').map((row) => row.name), ['Sala de aula']);
    assert.deepEqual(filterQrCheckpoints(prepared, 'SAÍDAS').map((row) => row.name), ['Pátio']);
    assert.deepEqual(filterQrCheckpoints(prepared, 'alimentacao').map((row) => row.name), ['Copa']);
    assert.equal(filterQrCheckpoints(prepared, '   ').length, prepared.length);
});
