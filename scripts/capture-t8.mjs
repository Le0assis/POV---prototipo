/**
 * Capturas da T8: página de QR, impressão com 2 por página e visitante
 * em alto contraste, fonte grande e painel aberto.
 */

import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

import { installApiMocks, startStaticServer } from '../tests/support/browser-harness.js';

const outDir = process.env.T8_OUT || '/opt/cursor/artifacts/t8';

const started = await startStaticServer();
const browser = await chromium.launch();

async function shot(page, name) {
    const file = path.join(outDir, name);
    await page.screenshot({ path: file, fullPage: false });
    console.log(file);
}

try {
    await mkdir(outDir, { recursive: true });

    for (const [width, height, suffix] of [[412, 915, '412'], [1280, 800, '1280']]) {
        const context = await browser.newContext({
            viewport: { width, height },
            reducedMotion: 'reduce'
        });
        const page = await context.newPage();
        await installApiMocks(page);
        await page.addInitScript(() => {
            sessionStorage.setItem('pov_editor_password', 'teste');
        });
        await page.goto(`${started.origin}/admin/qrcodes.html`, { waitUntil: 'networkidle' });
        await page.waitForSelector('.qr-card');
        await page.waitForSelector('.qr-warning');
        await shot(page, `qr-screen-${suffix}.png`);

        await page.emulateMedia({ media: 'print' });
        await shot(page, `qr-print-${suffix}.png`);
        if (suffix === '1280') {
            await page.pdf({
                path: path.join(outDir, 'qr-2-per-page.pdf'),
                format: 'A4',
                printBackground: true
            });
            console.log(path.join(outDir, 'qr-2-per-page.pdf'));
        }
        await context.close();
    }

    for (const [width, height, suffix] of [[412, 915, '412'], [1280, 800, '1280']]) {
        const context = await browser.newContext({
            viewport: { width, height },
            reducedMotion: 'reduce'
        });
        const page = await context.newPage();
        await installApiMocks(page);
        await page.addInitScript(() => {
            localStorage.setItem('pov.a11y', JSON.stringify({ hc: true, fontLg: true, speech: false }));
        });
        await page.goto(`${started.origin}/index.html`, { waitUntil: 'networkidle' });
        await page.waitForSelector('#a11y-button');
        await page.click('#a11y-button');
        await page.waitForSelector('#a11y-panel:not([hidden])');
        await shot(page, `visitor-a11y-${suffix}.png`);
        await context.close();
    }
} finally {
    await browser.close();
    await new Promise((resolve) => started.server.close(resolve));
}
