import assert from 'node:assert/strict';
import { test } from 'vitest';

import {
    MAP_CONFIG_HELP,
    PX_INVALID_MESSAGE,
    PX_MISSING_MESSAGE,
    formatMapConfigSaveError,
    validateMapConfigInput
} from '../src/pages/map-config-form.ts';

test('dicas da planta explicam imagem, px_per_m e rotação', () => {
    assert.match(MAP_CONFIG_HELP.plan_image, /vista de cima/);
    assert.match(MAP_CONFIG_HELP.px_per_m, /px_per_m = 100/);
    assert.match(MAP_CONFIG_HELP.rotation_deg, /sentido horário/);
});

test('px_per_m ausente ou <= 0 explica o 422', () => {
    assert.equal(validateMapConfigInput({ planImage: 'assets/planta.png', rawPx: '', degrees: 0 }).error, PX_MISSING_MESSAGE);
    assert.match(PX_MISSING_MESSAGE, /422/);
    assert.equal(validateMapConfigInput({ planImage: 'a', rawPx: '0', degrees: 0 }).error, PX_INVALID_MESSAGE);
    assert.equal(validateMapConfigInput({ planImage: 'a', rawPx: '-2', degrees: 0 }).error, PX_INVALID_MESSAGE);
    assert.match(PX_INVALID_MESSAGE, /422/);
});

test('entrada válida vira rotation_rad e o 422 do servidor aparece na mensagem', () => {
    const result = validateMapConfigInput({
        planImage: ' assets/planta.png ',
        rawPx: '12.5',
        degrees: 180
    });
    assert.equal(result.value.plan_image, 'assets/planta.png');
    assert.equal(result.value.px_per_m, 12.5);
    assert.ok(Math.abs(result.value.rotation_rad - Math.PI) < 1e-12);
    const message = formatMapConfigSaveError({ status: 422, message: 'px_per_m deve ser maior que zero' });
    assert.match(message, /422/);
    assert.match(message, /maior que zero/);
});
