import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

import {
    CAMERA_REASON,
    barcodeDetectorAvailable,
    cameraUnavailableReason,
    classifyCameraFailure,
    openRearCamera,
    setTorch,
    startQrScanner,
    stopStream,
    torchAvailable
} from '../js/qr/scanner.js';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function video() {
    return {
        srcObject: null,
        muted: false,
        autoplay: false,
        playsInline: false,
        readyState: 4,
        play: async () => {},
        pause() {},
        setAttribute() {}
    };
}

function streamFrom(track) {
    return {
        getTracks: () => [track],
        getVideoTracks: () => [track]
    };
}

test('HTTP e permissão negada têm motivo próprio', () => {
    assert.equal(cameraUnavailableReason({ secure: false, hasMedia: false, getUserMedia: null }), CAMERA_REASON.insecure);
    assert.equal(classifyCameraFailure({ name: 'NotAllowedError' }, { secure: true, hasMedia: true }), CAMERA_REASON.denied);
    assert.equal(classifyCameraFailure({ name: 'NotFoundError' }, { secure: true, hasMedia: true }), CAMERA_REASON.unavailable);
    assert.equal(classifyCameraFailure({ name: 'NotAllowedError' }, { secure: false, hasMedia: true }), CAMERA_REASON.insecure);
});

test('a câmera traseira pede environment e o fechar para a trilha', async () => {
    const stops = [];
    const track = {
        stop() {
            stops.push('stop');
        },
        getCapabilities: () => ({ torch: true }),
        applyConstraints: async (constraints) => {
            stops.push(constraints.advanced[0].torch);
        }
    };
    let seen = null;
    const stream = await openRearCamera(async (options) => {
        seen = options;
        return streamFrom(track);
    });
    assert.deepEqual(seen, { audio: false, video: { facingMode: { exact: 'environment' } } });
    assert.equal(torchAvailable(track), true);
    assert.equal(await setTorch(track, true), true);
    stopStream(stream);
    assert.deepEqual(stops, [true, 'stop']);
});

test('BarcodeDetector lê o QR e não carrega a lib', async () => {
    let loaded = 0;
    let formats = null;
    const stops = [];
    const track = {
        stop() {
            stops.push('stop');
        },
        getCapabilities: () => ({ torch: false })
    };
    class Detector {
        constructor(options) {
            formats = options.formats;
        }

        async detect() {
            return [{ rawValue: 'https://pov-unimar.com/#/scan?cp=recepcao&b=1&v=1' }];
        }
    }
    const seen = [];
    const handle = await startQrScanner(video(), {
        env: {
            secure: true,
            BarcodeDetector: Detector,
            getUserMedia: async () => streamFrom(track)
        },
        loadLibrary: async () => {
            loaded += 1;
            throw new Error('não devia carregar');
        },
        onCode: (text) => seen.push(text)
    });
    assert.equal(handle.backend, 'barcode-detector');
    assert.deepEqual(formats, ['qr_code']);
    assert.equal(loaded, 0);
    assert.match(seen[0], /cp=recepcao/);
    await handle.stop();
    assert.deepEqual(stops, ['stop']);
});

test('sem BarcodeDetector carrega o qr-scanner e o worker fica no vendor', async () => {
    const calls = [];
    const QrScanner = {
        NO_QR_CODE_FOUND: 'No QR code found',
        async createQrEngine() {
            calls.push('engine');
            return { kind: 'worker' };
        },
        async scanImage(_video, options) {
            calls.push(options.returnDetailedScanResult);
            assert.equal(options.qrEngine.kind, 'worker');
            return { data: 'recepcao' };
        }
    };
    const seen = [];
    const handle = await startQrScanner(video(), {
        env: {
            secure: true,
            BarcodeDetector: undefined,
            getUserMedia: async () => streamFrom({
                stop() {},
                getCapabilities: () => ({})
            })
        },
        loadLibrary: async () => QrScanner,
        onCode: (text) => seen.push(text)
    });
    assert.equal(handle.backend, 'qr-scanner');
    assert.deepEqual(calls, ['engine', true]);
    assert.equal(seen[0], 'recepcao');
    await handle.stop();

    const source = readFileSync(path.join(frontendRoot, 'js/qr/scanner.js'), 'utf8');
    assert.match(source, /BarcodeDetector/);
    assert.match(source, /formats: \['qr_code'\]/);
    assert.match(source, /facingMode: \{ exact: 'environment' \}/);
    assert.match(source, /vendor\/qr-scanner\/qr-scanner\.min\.js/);
    assert.equal(/https?:\/\//.test(source), false);
    const lib = readFileSync(path.join(frontendRoot, 'vendor/qr-scanner/qr-scanner.min.js'), 'utf8');
    const worker = readFileSync(path.join(frontendRoot, 'vendor/qr-scanner/qr-scanner-worker.min.js'), 'utf8');
    assert.match(lib, /qr-scanner-worker\.min\.js/);
    assert.match(worker, /export const createWorker/);
    assert.equal(await barcodeDetectorAvailable({ BarcodeDetector: undefined }), false);
});

test('página insegura não chama getUserMedia', async () => {
    let called = 0;
    await assert.rejects(
        () => startQrScanner(video(), {
            env: { secure: false, getUserMedia: async () => { called += 1; return null; } },
            onCode() {}
        }),
        (err) => err.reason === CAMERA_REASON.insecure
    );
    assert.equal(called, 0);
});
