import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import { afterAll, beforeAll, test } from 'vitest';

import {
    distRoot,
    formatViolations,
    installApiMocks,
    seriousViolations,
    startStaticServer
} from './support/browser-harness.js';

let server;
let origin;
let browser;

beforeAll(async () => {
    const started = await startStaticServer(distRoot);
    server = started.server;
    origin = started.origin;
    const { chromium } = await import('playwright');
    browser = await chromium.launch();
});

afterAll(async () => {
    if (browser) await browser.close();
    if (server) await new Promise((resolve) => server.close(resolve));
});

async function openPage(width = 412, height = 915) {
    const context = await browser.newContext({
        viewport: { width, height },
        reducedMotion: 'reduce'
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(String(error)));
    await installApiMocks(page);
    return { context, page, errors };
}

function axeReportFile(label) {
    const dir = process.env.AXE_REPORT_DIR;
    if (!dir) return '';
    const safe = String(label || 'pagina')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '') || 'pagina';
    return `${String(dir).replace(/[/\\]+$/, '')}/${safe}.json`;
}

/** Grava o JSON do axe só quando AXE_REPORT_DIR está definido (o job de CI). */
function writeAxeReport(label, results) {
    const file = axeReportFile(label);
    if (!file) return;
    const violations = Array.isArray(results && results.violations) ? results.violations : [];
    const incomplete = Array.isArray(results && results.incomplete) ? results.incomplete : [];
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, `${JSON.stringify({
        label,
        url: results && results.url ? results.url : '',
        timestamp: results && results.timestamp ? results.timestamp : new Date().toISOString(),
        violationCount: violations.length,
        incompleteCount: incomplete.length,
        violations,
        incomplete
    }, null, 2)}\n`);
}

async function expectClean(page, label) {
    const { default: AxeBuilder } = await import('@axe-core/playwright');
    const results = await new AxeBuilder({ page }).analyze();
    writeAxeReport(label, results);
    const serious = seriousViolations(results);
    assert.equal(serious.length, 0, `${label}\n${formatViolations(serious)}`);
    return results;
}

test('axe em index.html no E0', { timeout: 120000 }, async () => {
    const { context, page, errors } = await openPage();
    try {
        await page.goto(`${origin}/index.html`, { waitUntil: 'networkidle' });
        await page.waitForSelector('#a11y-button');
        await page.waitForSelector('.qr-button');
        await page.waitForSelector('#visitor-shell[data-state="E0"]');
        await expectClean(page, 'E0');
        assert.equal(errors.length, 0, errors.join('\n'));
    } finally {
        await context.close();
    }
});

test('axe em index.html com a folha de busca aberta', { timeout: 120000 }, async () => {
    const { context, page, errors } = await openPage();
    try {
        await page.goto(`${origin}/index.html`, { waitUntil: 'networkidle' });
        await page.waitForSelector('#search-field');
        await page.click('#search-field');
        await page.waitForSelector('#search-sheet-dialog:not([hidden])');
        await page.waitForSelector('#destination-list .destination-option');
        await expectClean(page, 'E2');
        assert.equal(errors.length, 0, errors.join('\n'));
    } finally {
        await context.close();
    }
});

test('axe em index.html no E4 com rota simulada', { timeout: 120000 }, async () => {
    const { context, page, errors } = await openPage();
    try {
        await page.addInitScript(() => {
            sessionStorage.setItem('pov.visitor.session', JSON.stringify({
                origin: { slug: 'recepcao', label: 'Recepção' },
                destination: { slug: 'sala', label: 'Sala de aula' },
                state: 'E3'
            }));
        });
        await page.goto(`${origin}/index.html?sensors=off#origem=recepcao&destino=sala`, { waitUntil: 'networkidle' });
        await page.waitForFunction(() => {
            const button = document.querySelector('.route-start');
            return button && !button.disabled && !button.closest('[hidden]');
        });
        await page.click('.route-start');
        await page.waitForSelector('#visitor-shell[data-state="E4"]');
        await page.waitForFunction(() => {
            const instruction = document.querySelector('.nav-instruction');
            return instruction && instruction.textContent.trim().length > 0;
        });
        await page.waitForSelector('.blue-dot.has-cone');
        await page.waitForFunction(() => {
            const labels = [...document.querySelectorAll('.you-label')]
                .filter((el) => (el.textContent || '').trim() === 'você');
            return labels.length === 1;
        });
        await expectClean(page, 'E4');
        assert.equal(errors.length, 0, errors.join('\n'));
    } finally {
        await context.close();
    }
});

test('axe em admin/qrcodes.html', { timeout: 120000 }, async () => {
    const { context, page, errors } = await openPage(1280, 800);
    try {
        await page.addInitScript(() => {
            sessionStorage.setItem('pov_editor_password', 'teste');
        });
        await page.goto(`${origin}/admin/qrcodes.html`, { waitUntil: 'networkidle' });
        await page.waitForSelector('#qr-app:not(.hidden)');
        await page.waitForSelector('.qr-card');
        await page.waitForSelector('.qr-warning');
        await expectClean(page, 'qrcodes');
        assert.equal(errors.length, 0, errors.join('\n'));
    } finally {
        await context.close();
    }
});
