/**
 * Helpers de DOM compartilhados.
 */

export function $(selector, root = document) {
    return root.querySelector(selector);
}

export function $$(selector, root = document) {
    return Array.from(root.querySelectorAll(selector));
}

const HTML_ESCAPES = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
};

/** Escapa texto para inserção segura via innerHTML. */
export function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value).replace(/[&<>"']/g, ch => HTML_ESCAPES[ch]);
}

/**
 * Preenche um <select> com nós do mapa, via DOM (sem concatenar HTML).
 * Aceita nós como objetos {id, label} ou strings.
 */
export function fillSelect(select, nodes, placeholder = '-- Selecione --') {
    if (!select) return;

    const options = [];

    const first = document.createElement('option');
    first.value = '';
    first.textContent = placeholder;
    options.push(first);

    (Array.isArray(nodes) ? nodes : []).forEach(node => {
        const isObject = node !== null && typeof node === 'object';
        const id = isObject ? (node.id ?? node.label ?? '') : node;
        const label = isObject ? (node.label ?? node.id ?? '') : node;

        const option = document.createElement('option');
        option.value = String(id);
        option.textContent = String(label);
        options.push(option);
    });

    select.replaceChildren(...options);
}

/** Formata número com `d` casas decimais; retorna '--' se inválido. */
export function formatNum(n, d = 1) {
    const num = Number(n);
    if (n === null || n === undefined || !Number.isFinite(num)) return '--';
    return num.toFixed(d);
}
