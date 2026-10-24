import assert from 'node:assert/strict';
import { test } from 'vitest';

import {
    API_URL_LOCAL,
    API_URL_REMOTE,
    resolveApiBaseUrl,
    testRoutesEnabled
} from '../src/core/config.ts';

test('VITE_API_URL define a API e a barra final sai', () => {
    assert.equal(resolveApiBaseUrl({ VITE_API_URL: 'https://lab.example/api/' }), 'https://lab.example/api');
});

test('VITE_API_URL ganha de VITE_API_BASE_URL', () => {
    assert.equal(resolveApiBaseUrl({
        VITE_API_URL: ' https://nova.example ',
        VITE_API_BASE_URL: 'https://antiga.example'
    }), 'https://nova.example');
});

test('sem VITE_API_URL, VITE_API_BASE_URL continua valendo', () => {
    assert.equal(resolveApiBaseUrl({
        VITE_API_URL: '  ',
        VITE_API_BASE_URL: 'http://127.0.0.1:8000/'
    }), 'http://127.0.0.1:8000');
});

test('sem variável, produção usa o host remoto e o dev usa o local', () => {
    assert.equal(resolveApiBaseUrl({ PROD: true }), API_URL_REMOTE);
    assert.equal(resolveApiBaseUrl({ PROD: false }), API_URL_LOCAL);
    assert.equal(API_URL_REMOTE, 'https://api.pov-unimar.com');
});

test('a localização de teste só liga no dev com a flag, nunca em produção', () => {
    assert.equal(testRoutesEnabled({ DEV: true, PROD: false, VITE_ENABLE_TEST_ROUTES: '1' }), true);
    assert.equal(testRoutesEnabled({ DEV: true, PROD: false, VITE_ENABLE_TEST_ROUTES: '0' }), false);
    assert.equal(testRoutesEnabled({ DEV: true, PROD: false }), false);
    assert.equal(testRoutesEnabled({ DEV: false, PROD: true, VITE_ENABLE_TEST_ROUTES: '1' }), false);
    assert.equal(testRoutesEnabled({ DEV: true, PROD: true, VITE_ENABLE_TEST_ROUTES: '1' }), false);
});
