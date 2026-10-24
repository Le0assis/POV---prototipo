/** Notificações temporárias. Substitui alert(). */

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
