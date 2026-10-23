import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

test('a raiz não guarda páginas que só redirecionam', () => {
    ['editor.html', 'recorder.html', 'routes.html'].forEach((file) => {
        assert.equal(existsSync(path.join(frontendRoot, file)), false, file);
    });
    assert.equal(existsSync(path.join(frontendRoot, 'admin/editor.html')), true);
    assert.equal(existsSync(path.join(frontendRoot, 'admin/recorder.html')), true);
});
