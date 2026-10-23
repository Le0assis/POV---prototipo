/**
 * Notificações (toast) e diálogo de confirmação acessível.
 * Substitui alert() e confirm().
 */

const MAX_VISIBLE_TOASTS = 2;

function getToastStack() {
    let stack = document.querySelector('.toast-stack');
    if (!stack) {
        stack = document.createElement('div');
        stack.className = 'toast-stack';
        stack.setAttribute('aria-live', 'polite');
        stack.setAttribute('aria-atomic', 'false');
        document.body.appendChild(stack);
    }
    return stack;
}

/**
 * Exibe uma notificação temporária.
 * @param {string} msg
 * @param {'info'|'ok'|'success'|'erro'|'error'} type
 * @param {number} ms
 */
export function toast(msg, type = 'info', ms = 3500) {
    const stack = getToastStack();

    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.setAttribute('role', type === 'erro' || type === 'error' ? 'alert' : 'status');
    el.textContent = String(msg ?? '');
    stack.appendChild(el);
    while (stack.childElementCount > MAX_VISIBLE_TOASTS && stack.firstElementChild) {
        stack.removeChild(stack.firstElementChild);
    }

    const remove = () => {
        if (el.parentNode) el.parentNode.removeChild(el);
    };
    setTimeout(remove, ms);
    el.addEventListener('click', remove);

    return el;
}

let dialogCounter = 0;

/**
 * Exibe um modal de confirmação.
 * @param {string} msg
 * @param {{okLabel?: string, cancelLabel?: string, danger?: boolean}} options
 * @returns {Promise<boolean>}
 */
export function confirmDialog(msg, { okLabel = 'Confirmar', cancelLabel = 'Cancelar', danger = false } = {} as any) {
    return new Promise(resolve => {
        const previousFocus = document.activeElement;
        const id = ++dialogCounter;

        const overlay = document.createElement('div');
        overlay.className = 'modal';

        const content = document.createElement('div');
        content.className = 'modal-content';
        content.setAttribute('role', 'alertdialog');
        content.setAttribute('aria-modal', 'true');
        content.setAttribute('aria-describedby', `confirm-msg-${id}`);

        const text = document.createElement('p');
        text.id = `confirm-msg-${id}`;
        text.textContent = String(msg ?? '');

        const actions = document.createElement('div');
        actions.style.display = 'flex';
        actions.style.gap = '12px';
        actions.style.justifyContent = 'flex-end';
        actions.style.marginTop = '20px';

        const cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'btn btn-ghost';
        cancelBtn.textContent = cancelLabel;

        const okBtn = document.createElement('button');
        okBtn.type = 'button';
        okBtn.className = `btn ${danger ? 'btn-danger' : 'btn-primary'}`;
        okBtn.textContent = okLabel;

        actions.append(cancelBtn, okBtn);
        content.append(text, actions);
        overlay.appendChild(content);

        let settled = false;
        const close = result => {
            if (settled) return;
            settled = true;
            document.removeEventListener('keydown', onKeyDown, true);
            overlay.remove();
            if (previousFocus && typeof (previousFocus as any).focus === 'function') {
                (previousFocus as any).focus();
            }
            resolve(result);
        };

        function onKeyDown(event) {
            if (event.key === 'Escape') {
                event.preventDefault();
                event.stopPropagation();
                close(false);
                return;
            }
            if (event.key === 'Tab') {
                // Mantém o foco preso dentro do diálogo.
                const focusables = [cancelBtn, okBtn];
                const index = focusables.indexOf(document.activeElement as HTMLButtonElement);
                event.preventDefault();
                let next;
                if (event.shiftKey) {
                    next = index <= 0 ? focusables.length - 1 : index - 1;
                } else {
                    next = index === focusables.length - 1 ? 0 : index + 1;
                }
                focusables[next].focus();
            }
        }

        okBtn.addEventListener('click', () => close(true));
        cancelBtn.addEventListener('click', () => close(false));
        overlay.addEventListener('click', event => {
            if (event.target === overlay) close(false);
        });
        document.addEventListener('keydown', onKeyDown, true);

        document.body.appendChild(overlay);
        // Ações destrutivas começam com foco em "Cancelar" por segurança.
        (danger ? cancelBtn : okBtn).focus();
    });
}
