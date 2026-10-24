import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'vitest';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

test('o Pages publica o build do Vite no domínio próprio', () => {
    const cname = readFileSync(path.join(root, 'frontend/public/CNAME'), 'utf8').trim();
    assert.equal(cname, 'pov-unimar.com');

    const vite = readFileSync(path.join(root, 'vite.config.ts'), 'utf8');
    assert.match(vite, /base:\s*'\/'/);

    const pages = readFileSync(path.join(root, '.github/workflows/pages.yml'), 'utf8');
    assert.match(pages, /actions\/deploy-pages/);
    assert.match(pages, /actions\/upload-pages-artifact/);
    assert.match(pages, /frontend\/dist/);
    assert.match(pages, /VITE_API_URL:\s*https:\/\/api\.pov-unimar\.com/);
    assert.match(pages, /VITE_API_BASE_URL:\s*https:\/\/api\.pov-unimar\.com/);
    assert.match(pages, /branches:\s*\["main"\]/);
    assert.doesNotMatch(pages, /feat\/pov-refatoracao/);

    const ci = readFileSync(path.join(root, '.github/workflows/frontend-deploy.yml'), 'utf8');
    assert.doesNotMatch(ci, /peaceiris\/actions-gh-pages/);
    assert.doesNotMatch(ci, /publish_dir:\s*\.\/frontend/);
});
