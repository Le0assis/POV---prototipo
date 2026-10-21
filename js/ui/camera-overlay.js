/**
 * Câmera em tela cheia para ler o QR do ponto.
 * Fecha pelo botão, pelo Escape e pelo voltar do Android (o app tira o estado E1 do histórico).
 */

import { CAMERA_REASON_TEXT, startQrScanner } from '../qr/scanner.js';
import { focusableElements, trapTabKey } from './focus-trap.js';

export function mountCameraOverlay(root, { onClose, onSubmit, onCameraFailure } = {}) {
    const overlay = document.createElement('div');
    overlay.className = 'camera-overlay';
    overlay.hidden = true;

    const dialog = document.createElement('section');
    dialog.className = 'camera-stage';
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('aria-labelledby', 'camera-title');
    dialog.setAttribute('aria-label', 'Ler QR code do ponto');

    const video = document.createElement('video');
    video.className = 'camera-video';
    video.muted = true;
    video.autoplay = true;
    video.playsInline = true;
    video.setAttribute('playsinline', '');
    video.setAttribute('aria-hidden', 'true');

    const frame = document.createElement('div');
    frame.className = 'camera-frame';
    frame.setAttribute('aria-hidden', 'true');

    const title = document.createElement('h2');
    title.id = 'camera-title';
    title.className = 'camera-hint';
    title.textContent = 'Aponte para o QR code do ponto';

    const status = document.createElement('div');
    status.className = 'camera-status';
    status.setAttribute('role', 'alert');
    status.hidden = true;

    const manual = document.createElement('form');
    manual.className = 'camera-manual';
    manual.hidden = true;
    const manualLabel = document.createElement('label');
    manualLabel.className = 'camera-manual-label';
    manualLabel.setAttribute('for', 'camera-manual-code');
    manualLabel.textContent = 'Código do ponto';
    const manualInput = document.createElement('input');
    manualInput.id = 'camera-manual-code';
    manualInput.className = 'text-field';
    manualInput.type = 'text';
    manualInput.autocomplete = 'off';
    manualInput.autocapitalize = 'off';
    manualInput.spellcheck = false;
    manualInput.enterKeyHint = 'go';
    manualInput.placeholder = 'Código do ponto';
    manualInput.setAttribute('aria-label', 'Código do ponto');
    const manualSubmit = document.createElement('button');
    manualSubmit.type = 'submit';
    manualSubmit.className = 'btn btn-primary';
    manualSubmit.textContent = 'Usar este código';
    manualSubmit.setAttribute('aria-label', 'Usar este código');
    manual.append(manualLabel, manualInput, manualSubmit);

    const actions = document.createElement('div');
    actions.className = 'camera-actions';

    const torch = document.createElement('button');
    torch.type = 'button';
    torch.className = 'btn btn-secondary camera-torch';
    torch.textContent = 'Lanterna';
    torch.setAttribute('aria-label', 'Ligar lanterna');
    torch.setAttribute('aria-pressed', 'false');
    torch.disabled = true;

    const typeCode = document.createElement('button');
    typeCode.type = 'button';
    typeCode.className = 'btn btn-secondary';
    typeCode.textContent = 'Digitar código';
    typeCode.setAttribute('aria-label', 'Digitar código');
    typeCode.setAttribute('aria-expanded', 'false');
    typeCode.setAttribute('aria-controls', 'camera-manual-code');

    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'btn btn-primary camera-close';
    close.textContent = 'Fechar';
    close.setAttribute('aria-label', 'Fechar câmera');

    actions.append(torch, typeCode, close);
    const dock = document.createElement('div');
    dock.className = 'camera-dock';
    dock.append(status, manual, actions);
    dialog.append(video, frame, title, dock);
    overlay.append(dialog);
    root.replaceChildren(overlay);

    let open = false;
    let restoreFocus = null;
    let scanner = null;
    let generation = 0;
    let torchOn = false;
    let inflight = false;
    let blockedText = '';
    let hold = false;

    function requestClose() {
        if (typeof onClose === 'function') onClose();
    }

    function onKey(event) {
        if (!open) return;
        if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            requestClose();
            return;
        }
        trapTabKey(dialog, event);
    }

    function setStatus(message, { retry } = {}) {
        status.replaceChildren();
        if (!message) {
            status.hidden = true;
            return;
        }
        status.hidden = false;
        const text = document.createElement('p');
        text.textContent = message;
        status.append(text);
        if (typeof retry === 'function') {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'btn btn-secondary';
            button.textContent = 'Tentar de novo';
            button.setAttribute('aria-label', 'Tentar de novo');
            button.addEventListener('click', () => {
                hold = false;
                blockedText = '';
                setStatus('');
                retry();
            });
            status.append(button);
        }
    }

    function syncTorch() {
        const supported = Boolean(scanner && scanner.hasTorch());
        torch.disabled = !supported;
        torch.setAttribute('aria-disabled', supported ? 'false' : 'true');
        if (!supported) {
            torch.setAttribute('aria-label', 'Lanterna indisponível nesta câmera');
            torch.setAttribute('aria-pressed', 'false');
            torch.textContent = 'Lanterna';
            return;
        }
        torch.setAttribute('aria-pressed', torchOn ? 'true' : 'false');
        torch.setAttribute('aria-label', torchOn ? 'Desligar lanterna' : 'Ligar lanterna');
        torch.textContent = torchOn ? 'Desligar lanterna' : 'Lanterna';
    }

    async function submitText(text, source) {
        const raw = String(text || '').trim();
        if (!raw || inflight) return;
        if (source === 'camera' && (hold || raw === blockedText)) return;
        inflight = true;
        if (scanner) scanner.pause();
        try {
            const result = typeof onSubmit === 'function' ? await onSubmit(raw, source) : 'invalid';
            if (!open) return;
            if (result === 'ok' || result === 'stale') {
                blockedText = raw;
                return;
            }
            if (result === 'not-found') {
                blockedText = raw;
                setStatus('QR não reconhecido neste prédio');
            } else if (result === 'unsupported') {
                blockedText = raw;
                setStatus('Versão do QR não suportada.');
            } else if (result === 'network') {
                hold = true;
                blockedText = raw;
                setStatus('Tentar de novo', { retry: () => submitText(raw, 'manual') });
            } else {
                blockedText = raw;
                setStatus('Este QR não é de um ponto.');
            }
        } finally {
            inflight = false;
            if (scanner && open && !hold) scanner.resume();
        }
    }

    async function stopScanner() {
        const current = scanner;
        scanner = null;
        torchOn = false;
        if (current) {
            try {
                await current.stop();
            } catch (_) {
                /* a câmera já pode ter sido solta */
            }
        }
        syncTorch();
    }

    async function startScanner(token) {
        try {
            const handle = await startQrScanner(video, {
                onCode: (text) => {
                    if (token !== generation || !open) return;
                    submitText(text, 'camera');
                },
                onMiss: () => {
                    if (!inflight && !hold) blockedText = '';
                }
            });
            if (token !== generation || !open) {
                await handle.stop();
                return;
            }
            scanner = handle;
            syncTorch();
        } catch (err) {
            if (token !== generation || !open) return;
            const reason = err && err.reason ? err.reason : 'generic';
            const message = (err && err.message) || CAMERA_REASON_TEXT[reason] || CAMERA_REASON_TEXT.generic;
            if (typeof onCameraFailure === 'function') onCameraFailure({ reason, message });
        }
    }

    function setManualOpen(show) {
        manual.hidden = !show;
        typeCode.setAttribute('aria-expanded', show ? 'true' : 'false');
        if (show) manualInput.focus();
    }

    async function setOpen(next) {
        const show = Boolean(next);
        if (show === open) {
            if (show) {
                const nodes = focusableElements(dialog);
                if (nodes[0]) nodes[0].focus();
            }
            return;
        }
        open = show;
        overlay.hidden = !show;
        if (!show) {
            generation += 1;
            document.removeEventListener('keydown', onKey, true);
            setStatus('');
            setManualOpen(false);
            manualInput.value = '';
            inflight = false;
            blockedText = '';
            hold = false;
            await stopScanner();
            const back = restoreFocus;
            restoreFocus = null;
            if (back && typeof back.focus === 'function' && document.contains(back)) back.focus();
            return;
        }
        restoreFocus = document.activeElement;
        document.addEventListener('keydown', onKey, true);
        setStatus('');
        setManualOpen(false);
        close.focus();
        const token = ++generation;
        startScanner(token);
    }

    torch.addEventListener('click', async () => {
        if (!scanner || torch.disabled) return;
        const next = !torchOn;
        try {
            const applied = await scanner.setTorch(next);
            if (!applied) return;
            torchOn = next;
            syncTorch();
        } catch (_) {
            torchOn = false;
            syncTorch();
        }
    });

    typeCode.addEventListener('click', () => {
        setManualOpen(manual.hidden);
    });

    manual.addEventListener('submit', (event) => {
        event.preventDefault();
        submitText(manualInput.value, 'manual');
    });

    close.addEventListener('click', requestClose);

    return {
        setOpen,
        isOpen: () => open,
        element: dialog,
        setStatus,
        video
    };
}
