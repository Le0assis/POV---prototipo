import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const pages = [
    ['editor.html', 'admin/editor.html'],
    ['recorder.html', 'admin/recorder.html']
];

test('editor.html e recorder.html redirecionam preservando query e hash', () => {
    pages.forEach(([file, target]) => {
        const html = readFileSync(path.join(frontendRoot, file), 'utf8');
        assert.match(html, /http-equiv="refresh"/i, file);
        assert.match(html, new RegExp(`content="0;url=${target.replace('/', '\\/')}"`), file);
        assert.match(
            html,
            new RegExp(`location\\.replace\\('${target}' \\+ location\\.search \\+ location\\.hash\\)`),
            file
        );
        assert.match(html, new RegExp(`href="${target}"`), file);
        assert.doesNotMatch(html, /floor-map/, file);
    });
});
