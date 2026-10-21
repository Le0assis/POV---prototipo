/**
 * Folha inferior da busca. Nesta tarefa ela abre e fecha vazia:
 * a lista de destinos entra na T4.
 */

import { focusableElements, trapTabKey } from './focus-trap.js';

export function mountSearchSheet(root, { onClose } = {}) {
    const scrim = document.createElement('button');
    scrim.type = 'button';
    scrim.className = 'sheet-scrim';
    scrim.tabIndex = -1;
    scrim.setAttribute('aria-label', 'Fechar busca');
    scrim.hidden = true;

    const sheet = document.createElement('section');
    sheet.className = 'bottom-sheet visitor-sheet';
    sheet.id = 'search-sheet-dialog';
    sheet.setAttribute('role', 'dialog');
    sheet.setAttribute('aria-modal', 'true');
    sheet.setAttribute('aria-labelledby', 'search-sheet-title');
    sheet.setAttribute('aria-label', 'Busca de destino');
    sheet.hidden = true;

    const handle = document.createElement('button');
    handle.type = 'button';
    handle.className = 'sheet-handle';
    handle.setAttribute('aria-label', 'Arrastar para fechar a busca');
    const grip = document.createElement('span');
    grip.className = 'bottom-sheet-handle';
    grip.setAttribute('aria-hidden', 'true');
    handle.append(grip);

    const head = document.createElement('div');
    head.className = 'sheet-head';
    const title = document.createElement('h2');
    title.id = 'search-sheet-title';
    title.textContent = 'Para onde você quer ir?';
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'btn btn-ghost sheet-close';
    close.textContent = 'Fechar';
    close.setAttribute('aria-label', 'Fechar busca');
    head.append(title, close);

    const body = document.createElement('div');
    body.className = 'sheet-body';
    body.setAttribute('aria-label', 'Resultados da busca');

    sheet.append(handle, head, body);
    root.replaceChildren(scrim, sheet);

    let open = false;
    let restoreFocus = null;
    let dragStart = 0;
    let dragging = false;

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
        trapTabKey(sheet, event);
    }

    function setOpen(next, { focus } = {}) {
        const show = Boolean(next);
        if (show === open) {
            if (show && focus) focusSheet();
            return;
        }
        open = show;
        scrim.hidden = !show;
        sheet.hidden = !show;
        sheet.style.transform = '';
        if (show) {
            restoreFocus = document.activeElement;
            document.addEventListener('keydown', onKey, true);
            focusSheet();
        } else {
            document.removeEventListener('keydown', onKey, true);
            const back = restoreFocus;
            restoreFocus = null;
            if (back && typeof back.focus === 'function' && document.contains(back)) back.focus();
        }
    }

    function focusSheet() {
        const nodes = focusableElements(sheet);
        const target = nodes.find((el) => el !== handle) || nodes[0];
        if (target) target.focus();
    }

    scrim.addEventListener('click', requestClose);
    close.addEventListener('click', requestClose);
    handle.addEventListener('click', (event) => {
        if (dragging) {
            event.preventDefault();
            return;
        }
        requestClose();
    });

    handle.addEventListener('pointerdown', (event) => {
        dragging = false;
        dragStart = event.clientY;
        handle.setPointerCapture(event.pointerId);
    });
    handle.addEventListener('pointermove', (event) => {
        const delta = event.clientY - dragStart;
        if (delta > 8) dragging = true;
        if (delta > 0) sheet.style.transform = `translateY(${delta}px)`;
    });
    handle.addEventListener('pointerup', (event) => {
        const delta = event.clientY - dragStart;
        sheet.style.transform = '';
        if (delta > 48) requestClose();
        window.setTimeout(() => {
            dragging = false;
        }, 0);
    });
    handle.addEventListener('pointercancel', () => {
        sheet.style.transform = '';
        dragging = false;
    });

    return {
        setOpen,
        isOpen: () => open,
        element: sheet
    };
}
