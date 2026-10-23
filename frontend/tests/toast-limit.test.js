import assert from 'node:assert/strict';
import { test, vi } from 'vitest';

import { toast } from '../src/core/toast.ts';

function installDom() {
    const nodes = [];
    function make(tag) {
        const node = {
            tagName: String(tag).toUpperCase(),
            className: '',
            textContent: '',
            parentNode: null,
            children: [],
            setAttribute() {},
            addEventListener() {},
            appendChild(child) {
                child.parentNode = node;
                node.children.push(child);
                return child;
            },
            removeChild(child) {
                const index = node.children.indexOf(child);
                if (index >= 0) node.children.splice(index, 1);
                child.parentNode = null;
                return child;
            },
            get childElementCount() { return node.children.length; },
            get firstElementChild() { return node.children[0] || null; }
        };
        nodes.push(node);
        return node;
    }
    const body = make('body');
    const previous = globalThis.document;
    globalThis.document = {
        body,
        createElement: make,
        querySelector(selector) {
            if (selector !== '.toast-stack') return null;
            return nodes.find((node) => node.className === 'toast-stack') || null;
        }
    };
    return {
        restore() {
            globalThis.document = previous;
        }
    };
}

test('no máximo dois toasts ficam visíveis e o mais antigo sai', () => {
    vi.useFakeTimers();
    const dom = installDom();
    try {
        const texts = ['um', 'dois', 'três', 'quatro'];
        texts.forEach((text) => toast(text, 'erro', 8000));
        const stack = document.querySelector('.toast-stack');
        assert.equal(stack.childElementCount, 2);
        assert.deepEqual(stack.children.map((node) => node.textContent), ['três', 'quatro']);
        assert.equal(stack.className, 'toast-stack');
    } finally {
        vi.useRealTimers();
        dom.restore();
    }
});
