import assert from 'node:assert/strict';
import { test } from 'vitest';

import { pixelTolerance, pointsUntil, routeSignature, simplifyPath } from '../src/map/simplify.ts';

test('reta com vértices colineares fica com as pontas', () => {
    const points = [
        { x: 0, y: 0 },
        { x: 1, y: 0 },
        { x: 2, y: 0 },
        { x: 10, y: 0 }
    ];
    const simplified = simplifyPath(points, 0.5);
    assert.equal(simplified.length, 2);
    assert.equal(simplified[0].x, 0);
    assert.equal(simplified[1].x, 10);
});

test('um desvio maior que a tolerância permanece', () => {
    const points = [
        { x: 0, y: 0 },
        { x: 5, y: 8 },
        { x: 10, y: 0 }
    ];
    const simplified = simplifyPath(points, 1);
    assert.equal(simplified.length, 3);
});

test('a tolerância cresce com px_per_m e o progresso corta a polilinha', () => {
    assert.equal(pixelTolerance(10), 2.5);
    const walked = pointsUntil([{ x: 0, y: 0 }, { x: 10, y: 0 }], 0.5);
    assert.equal(walked.length, 2);
    assert.equal(walked[1].x, 5);
    const signature = routeSignature({ points: [{ x: 0, y: 0 }, { x: 4, y: 0 }], distance_m: 4 });
    assert.equal(signature, routeSignature({ points: [{ x: 0, y: 0 }, { x: 4, y: 0 }], distance_m: 4 }));
    assert.notEqual(signature, routeSignature({ points: [{ x: 0, y: 0 }, { x: 9, y: 0 }], distance_m: 9 }));
});
