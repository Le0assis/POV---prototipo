import assert from 'node:assert/strict';
import { test } from 'vitest';

import {
    QR_PAGE,
    QrErrorCode,
    QrFormatError,
    buildQr,
    parseQr,
    parseScanLocation
} from '../src/qr/qr-format.ts';

const accented = 'sala de reunião';

test('a URL v1 faz a ida e a volta, com espaço e acento codificados', () => {
    const url = buildQr({ cp: accented, b: 2 });
    assert.match(url, /^https:\/\/pov-unimar\.com\/#\/scan\?/);
    assert.equal(url.startsWith(QR_PAGE), true);
    assert.equal(url.includes(' '), false);
    assert.match(url, /cp=sala%20de%20reuni%C3%A3o/);
    assert.match(url, /b=2/);
    assert.match(url, /v=1/);
    assert.deepEqual(parseQr(url), { cp: accented, b: 2, v: 1 });
});

test('aceita outro host ou caminho, omite b e assume v 1', () => {
    assert.deepEqual(parseQr('https://example.org/qualquer/caminho?cp=recepcao&b=4'), {
        cp: 'recepcao',
        b: 4,
        v: 1
    });
    assert.deepEqual(parseQr('https://10.0.0.8:8080/app/index.html?cp=porta'), {
        cp: 'porta',
        b: null,
        v: 1
    });
    assert.deepEqual(parseQr('https://pov-unimar.com/#/scan?cp=hall&b=3'), {
        cp: 'hall',
        b: 3,
        v: 1
    });
    assert.deepEqual(parseQr('#/scan?cp=sala+de+reuni%C3%A3o&b=1&v=1'), {
        cp: accented,
        b: 1,
        v: 1
    });
});

test('o hash #origem= e o slug digitado também valem', () => {
    assert.deepEqual(parseQr(`#origem=${encodeURIComponent(accented)}`), {
        cp: accented,
        b: null,
        v: 1
    });
    assert.deepEqual(parseQr('#origem=recepcao&destino=copa'), {
        cp: 'recepcao',
        b: null,
        v: 1
    });
    assert.deepEqual(parseQr('  recepcao  '), { cp: 'recepcao', b: null, v: 1 });
    assert.deepEqual(parseQr('Sala de Reunião'), { cp: 'Sala de Reunião', b: null, v: 1 });
    assert.equal(parseScanLocation('#origem=recepcao'), null);
    assert.deepEqual(parseScanLocation('#/scan?cp=recepcao&b=1&v=1'), {
        cp: 'recepcao',
        b: 1,
        v: 1
    });
    assert.deepEqual(parseScanLocation('https://pov-unimar.com/#/scan?cp=hall&b=8&v=1').cp, 'hall');
});

test('rejeita vazio, URL sem cp e prédio inválido', () => {
    for (const sample of ['', '   ', 'https://example.com/x', '#/scan?b=1', '#/scan?cp=', '#origem=', '???', 'https://']) {
        const parsed = parseQr(sample);
        assert.equal(parsed.error, QrErrorCode.invalid, sample);
        assert.equal(parsed.cp, undefined, sample);
    }
    assert.equal(parseQr('#/scan?cp=recepcao&b=bloco').error, QrErrorCode.invalid);
    assert.throws(() => buildQr({ cp: '  ' }), (err) => err instanceof QrFormatError && err.code === 'invalid');
});

test('versão diferente de 1 é erro tipado', () => {
    for (const sample of [
        'https://pov-unimar.com/#/scan?cp=recepcao&b=1&v=2',
        '#/scan?cp=recepcao&v=0',
        '#/scan?cp=recepcao&v=1.5',
        '#/scan?cp=recepcao&v=abc',
        buildQr({ cp: 'recepcao', b: 1 }).replace('v=1', 'v=9')
    ]) {
        const parsed = parseQr(sample);
        assert.equal(parsed.error, QrErrorCode.unsupportedVersion, sample);
    }
    assert.equal(parseScanLocation('#/scan?cp=recepcao&v=2').error, QrErrorCode.unsupportedVersion);
});
