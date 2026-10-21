/**
 * Mantém o Tab dentro de um diálogo aberto.
 */

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

export function focusableElements(container) {
    if (!container) return [];
    return Array.from(container.querySelectorAll(FOCUSABLE)).filter((el) => {
        if (el.disabled) return false;
        if (el.getAttribute('aria-hidden') === 'true') return false;
        if (el.closest('[hidden]')) return false;
        return true;
    });
}

export function trapTabKey(container, event) {
    if (!container || event.key !== 'Tab') return;
    const nodes = focusableElements(container);
    if (nodes.length === 0) {
        event.preventDefault();
        return;
    }
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    const active = document.activeElement;
    const inside = container.contains(active);
    if (event.shiftKey && (!inside || active === first)) {
        event.preventDefault();
        last.focus();
    } else if (!event.shiftKey && (!inside || active === last)) {
        event.preventDefault();
        first.focus();
    }
}
