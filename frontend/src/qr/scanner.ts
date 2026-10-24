/**
 * Câmera traseira para QR.
 * `BarcodeDetector` (formats: qr_code) quando o Chrome oferece.
 * Senão, carrega sob demanda o `qr-scanner` da Nimiq em `frontend/vendor/qr-scanner/`
 * (ESM + worker ao lado; nada de CDN em runtime).
 */

export const CAMERA_REASON = Object.freeze({
    insecure: 'insecure',
    denied: 'denied',
    unavailable: 'unavailable',
    generic: 'generic'
});

export const CAMERA_REASON_TEXT = Object.freeze({
    insecure: 'A câmera só abre em HTTPS. Digite o código do ponto.',
    denied: 'A permissão da câmera foi negada. Libere o acesso nas configurações do navegador ou digite o código do ponto.',
    unavailable: 'Nenhuma câmera disponível neste aparelho. Digite o código do ponto.',
    generic: 'Não foi possível abrir a câmera. Digite o código do ponto.'
});

const SCAN_INTERVAL_MS = 200;

export function classifyCameraFailure(error, { secure = true, hasMedia = true } = {} as any) {
    if (!secure) return CAMERA_REASON.insecure;
    if (!hasMedia) return CAMERA_REASON.unavailable;
    const name = error && error.name;
    if (name === 'NotAllowedError') return CAMERA_REASON.denied;
    if (name === 'SecurityError') return CAMERA_REASON.denied;
    if (name === 'NotFoundError' || name === 'OverconstrainedError' || name === 'NotReadableError') {
        return CAMERA_REASON.unavailable;
    }
    return CAMERA_REASON.generic;
}

export function cameraEnvironment(env = {} as any) {
    const root = env.root || (typeof window !== 'undefined' ? window : globalThis);
    const nav = env.navigator || (typeof navigator !== 'undefined' ? navigator : null);
    const secure = env.secure != null
        ? Boolean(env.secure)
        : !(root && root.isSecureContext === false);
    const media = nav && nav.mediaDevices;
    const getUserMedia = env.getUserMedia
        || (media && typeof media.getUserMedia === 'function' ? media.getUserMedia.bind(media) : null);
    return {
        secure,
        hasMedia: Boolean(getUserMedia),
        getUserMedia,
        BarcodeDetector: env.BarcodeDetector !== undefined
            ? env.BarcodeDetector
            : root && root.BarcodeDetector,
        root
    };
}

/** `null` quando dá para pedir a câmera. */
export function cameraUnavailableReason(env = cameraEnvironment()) {
    if (!env.secure) return CAMERA_REASON.insecure;
    if (!env.hasMedia || typeof env.getUserMedia !== 'function') return CAMERA_REASON.unavailable;
    return null;
}

export function torchAvailable(track) {
    if (!track || typeof track.getCapabilities !== 'function') return false;
    try {
        const caps = track.getCapabilities();
        return Boolean(caps && caps.torch);
    } catch (_) {
        return false;
    }
}

export async function setTorch(track, on) {
    if (!torchAvailable(track) || typeof track.applyConstraints !== 'function') return false;
    await track.applyConstraints({ advanced: [{ torch: Boolean(on) }] });
    return true;
}

export function stopStream(stream) {
    if (!stream || typeof stream.getTracks !== 'function') return;
    stream.getTracks().forEach((track) => {
        try {
            track.stop();
        } catch (_) {
            /* a trilha já pode ter sido parada */
        }
    });
}

/**
 * Tenta a traseira (`facingMode: environment`) e, se o aparelho recusar o modo,
 * qualquer câmera. Permissão negada não tenta de novo.
 */
export async function openRearCamera(getUserMedia) {
    const attempts = [
        { facingMode: { exact: 'environment' } },
        { facingMode: { ideal: 'environment' } },
        true
    ];
    let lastError = null;
    for (const video of attempts) {
        try {
            return await getUserMedia({ audio: false, video });
        } catch (err) {
            lastError = err;
            const name = err && err.name;
            if (name === 'NotAllowedError' || name === 'SecurityError') throw err;
        }
    }
    throw lastError || Object.assign(new Error('Camera not found.'), { name: 'NotFoundError' });
}

export async function barcodeDetectorAvailable(env) {
    const Detector = env && env.BarcodeDetector;
    if (typeof Detector !== 'function') return false;
    if (typeof Detector.getSupportedFormats === 'function') {
        try {
            const formats = await Detector.getSupportedFormats();
            if (Array.isArray(formats) && !formats.includes('qr_code')) return false;
        } catch (_) {
            return false;
        }
    }
    return true;
}

export async function loadQrScannerModule() {
    const mod = await import('../../vendor/qr-scanner/qr-scanner.min.js');
    return mod.default || mod;
}

function cameraError(reason, cause = undefined) {
    const error = new Error(CAMERA_REASON_TEXT[reason] || CAMERA_REASON_TEXT.generic) as any;
    error.reason = reason;
    if (cause) error.cause = cause;
    return error;
}

function rawValue(code) {
    if (!code) return '';
    if (typeof code === 'string') return code;
    if (code.rawValue != null) return String(code.rawValue);
    if (code.data != null) return String(code.data);
    return '';
}

function videoReady(video) {
    if (!video) return false;
    if (video.readyState == null) return true;
    return video.readyState >= 2;
}

function prepareVideo(video, stream) {
    if (!video) return;
    video.srcObject = stream;
    video.muted = true;
    video.autoplay = true;
    video.playsInline = true;
    if (typeof video.setAttribute === 'function') {
        video.setAttribute('playsinline', '');
        video.setAttribute('muted', '');
        video.setAttribute('autoplay', '');
        video.setAttribute('aria-hidden', 'true');
    }
}

/**
 * Abre a câmera e fica lendo. `onCode` recebe o texto.
 * `onMiss` avisa quando o quadro não tem QR (para liberar um código rejeitado).
 * `stop` encerra o timer e as trilhas.
 */
export async function startQrScanner(video, options = {} as any) {
    const env = cameraEnvironment(options.env || {});
    const blocked = cameraUnavailableReason(env);
    if (blocked) throw cameraError(blocked);

    let stream;
    try {
        stream = await openRearCamera(options.getUserMedia || env.getUserMedia);
    } catch (err) {
        throw cameraError(classifyCameraFailure(err, env), err);
    }

    prepareVideo(video, stream);
    try {
        if (video && typeof video.play === 'function') await video.play();
    } catch (err) {
        stopStream(stream);
        if (video) video.srcObject = null;
        throw cameraError(classifyCameraFailure(err, env), err);
    }

    const track = stream.getVideoTracks ? stream.getVideoTracks()[0] : stream.getTracks()[0];
    let stopped = false;
    let paused = false;
    let timer = null;
    let engine = null;
    let backend = 'qr-scanner';

    function schedule(fn) {
        if (stopped) return;
        timer = setTimeout(fn, SCAN_INTERVAL_MS);
    }

    const useDetector = await barcodeDetectorAvailable(env);
    if (useDetector) {
        backend = 'barcode-detector';
        let detector;
        try {
            detector = new env.BarcodeDetector({ formats: ['qr_code'] });
        } catch (err) {
            backend = 'qr-scanner';
            detector = null;
            if (options.onDetectorFailure) options.onDetectorFailure(err);
        }
        if (detector) {
            const tick = async () => {
                if (stopped) return;
                if (!paused && videoReady(video)) {
                    try {
                        const codes = await detector.detect(video);
                        const text = rawValue(codes && codes[0]);
                        if (text) {
                            if (typeof options.onCode === 'function') options.onCode(text);
                        } else if (typeof options.onMiss === 'function') {
                            options.onMiss();
                        }
                    } catch (_) {
                        if (typeof options.onMiss === 'function') options.onMiss();
                    }
                }
                if (!stopped) schedule(tick);
            };
            void tick();
        }
    }

    if (backend !== 'barcode-detector') {
        const load = options.loadLibrary || loadQrScannerModule;
        let QrScanner;
        try {
            QrScanner = await load();
            engine = typeof QrScanner.createQrEngine === 'function'
                ? await QrScanner.createQrEngine()
                : null;
        } catch (err) {
            stopStream(stream);
            if (video) video.srcObject = null;
            throw cameraError(CAMERA_REASON.unavailable, err);
        }
        const tick = async () => {
            if (stopped) return;
            if (!paused && videoReady(video)) {
                try {
                    const result = await QrScanner.scanImage(video, {
                        qrEngine: engine,
                        returnDetailedScanResult: true
                    });
                    const text = rawValue(result);
                    if (text) {
                        if (typeof options.onCode === 'function') options.onCode(text);
                    } else if (typeof options.onMiss === 'function') {
                        options.onMiss();
                    }
                } catch (err) {
                    const missing = err === QrScanner.NO_QR_CODE_FOUND
                        || (err && err.message === QrScanner.NO_QR_CODE_FOUND);
                    if (missing && typeof options.onMiss === 'function') options.onMiss();
                }
            }
            if (!stopped) schedule(tick);
        };
        void tick();
    }

    return {
        backend,
        hasTorch: () => torchAvailable(track),
        setTorch: (on) => setTorch(track, on),
        pause: () => {
            paused = true;
        },
        resume: () => {
            paused = false;
        },
        async stop() {
            if (stopped) return;
            stopped = true;
            if (timer) clearTimeout(timer);
            timer = null;
            stopStream(stream);
            if (video) {
                try {
                    if (typeof video.pause === 'function') video.pause();
                } catch (_) {
                    /* ignora */
                }
                video.srcObject = null;
            }
            if (typeof Worker !== 'undefined' && engine instanceof Worker) {
                try {
                    engine.terminate();
                } catch (_) {
                    /* ignora */
                }
            }
            engine = null;
        }
    };
}
