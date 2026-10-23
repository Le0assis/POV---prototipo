import assert from 'node:assert/strict';
import test from 'node:test';

import { addCheckpoint, addManualConnection, patchCheckpointPosition } from '../js/pages/editor-model.js';
import { loadFloorModel } from '../js/pages/floor-model.js';

function emptyModel() {
    return {
        checkpoints: [],
        byName: new Map(),
        config: { plan_image: '', px_per_m: 10, rotation_rad: 0, ready: true },
        connections: [],
        polylines: [],
        missingAnchor: []
    };
}

test('posição salva atualiza o nó sem recriar a lista', () => {
    const model = emptyModel();
    addCheckpoint(model, { name: 'Sala' });
    const same = model.checkpoints[0];
    assert.equal(patchCheckpointPosition(model, 'Sala', { pos_x_px: 12, pos_y_px: 8 }), true);
    assert.equal(model.checkpoints[0], same);
    assert.equal(same.anchor.pos_x_px, 12);
    assert.equal(same.anchor.pos_y_px, 8);
});

test('conexão manual entra no modelo e desenha a reta', () => {
    const model = emptyModel();
    addCheckpoint(model, { name: 'A', pos_x_px: 0, pos_y_px: 0 });
    addManualConnection(model, { source: 'A', target: 'B', distance_m: 10, heading_rad: 0 });
    assert.equal(model.connections.length, 1);
    assert.equal(model.polylines.length, 1);
    assert.equal(model.polylines[0].recorded, false);
});

test('mapa, planta e conexões são pedidos ao mesmo tempo', async () => {
    let open = 0;
    let max = 0;
    const delay = (value) => new Promise((resolve) => {
        open += 1;
        max = Math.max(max, open);
        setTimeout(() => {
            open -= 1;
            resolve(value);
        }, 40);
    });
    const model = await loadFloorModel({
        api: {
            getMap: () => delay({ nodes: [{ name: 'Sala', pos_x_px: 1, pos_y_px: 2 }] }),
            getMapConfig: () => delay({ map_config: { plan_image: 'a.png', px_per_m: 10, rotation_rad: 0 } }),
            getConnections: ({ includePath }) => {
                assert.equal(includePath, false);
                return delay({ connections: [] });
            }
        },
        includePath: false
    });
    assert.equal(max, 3);
    assert.equal(model.checkpoints[0].name, 'Sala');
    assert.equal(model.config.px_per_m, 10);
});
