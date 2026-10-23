import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import { TEST_ROUTES_ENABLED, localizeBody, serverLocationPaths } from './fixtures/server-location.js';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

test('a flag de rotas de teste nasce desligada', () => {
    assert.equal(TEST_ROUTES_ENABLED, false);
    assert.deepEqual(localizeBody(0.7, 1), { step_length_m: 0.7, yaw_rad: 1 });
});

test('o aplicativo não chama localize, current_location nem reset', () => {
    const forbidden = serverLocationPaths();
    const files = [];
    const walk = (dir) => {
        for (const entry of readdirSync(dir, { withFileTypes: true })) {
            if (entry.name === 'vendor' || entry.name === 'node_modules') continue;
            const full = path.join(dir, entry.name);
            if (entry.isDirectory()) walk(full);
            else if (/\.(js|html)$/.test(entry.name)) files.push(full);
        }
    };
    walk(path.join(frontendRoot, 'js'));
    walk(path.join(frontendRoot, 'admin'));
    ['index.html', 'viewer.html', 'locate.html', 'routes.html', 'editor.html', 'recorder.html']
        .forEach((name) => {
            const full = path.join(frontendRoot, name);
            try {
                files.push(full);
                readFileSync(full);
            } catch (_) {
                files.pop();
            }
        });
    files.forEach((file) => {
        const text = readFileSync(file, 'utf8');
        forbidden.forEach((token) => {
            assert.equal(text.includes(token), false, `${file} contém ${token}`);
        });
    });
});
