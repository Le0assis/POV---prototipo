/**
 * Espaço reservado da câmera. A leitura do QR não entra nesta tarefa.
 */

import { focusableElements, trapTabKey } from './focus-trap.js';

export function mountCameraOverlay(root, { onClose } = {}) {
    const overlay = document.createElement('div');
    overlay.className = 'camera-overlay';
    overlay.hidden = true;

    const scrim = document.createElement('button');
    scrim.type = 'button';
    scrim.className = 'camera-scrim';
    scrim.tabIndex = -1;
    scrim.setAttribute('aria-label', 'Fechar câmera');

    const dialog = document.createElement('section');
    dialog.className = 'camera-card';
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('aria-labelledby', 'camera-title');
    dialog.setAttribute('aria-label', 'Câmera para ler QR');

    const title = document.createElement('h2');
    title.id = 'camera-title';
    title.textContent = 'Câmera';

    const frame = document.createElement('div');
    frame.className = 'camera-frame';
    frame.setAttribute('aria-hidden', 'true');
    const hint = document.createElement('p');
    hint.className = 'camera-placeholder';
    hint.textContent = 'A leitura do QR entra numa próxima etapa.';

    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'btn btn-primary camera-close';
    close.textContent = 'Fechar';
    close.setAttribute('aria-label', 'Fechar câmera');

    dialog.append(title, frame, hint, close);
    overlay.append(scrim, dialog);
    root.replaceChildren(overlay);

    let open = false;
    let restoreFocus = null;

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

    function setOpen(next) {
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
        if (show) {
            restoreFocus = document.activeElement;
            document.addEventListener('keydown', onKey, true);
            close.focus();
        } else {
            document.removeEventListener('keydown', onKey, true);
            const back = restoreFocus;
            restoreFocus = null;
            if (back && typeof back.focus === 'function' && document.contains(back)) back.focus();
        }
    }

    scrim.addEventListener('click', requestClose);
    close.addEventListener('click', requestClose);

    return { setOpen, isOpen: () => open, element: dialog };
}
