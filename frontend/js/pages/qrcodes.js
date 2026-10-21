/**
 * Gerar QR codes. A senha do editor continua na porta da administração.
 * A lista usa o adaptador de checkpoints. O desenho fica no qrcode-generator local.
 */

import { getMap } from '../core/api.js';
import { whenAdminGranted } from '../core/role-toggle.js';
import { insertTopNav } from '../components/nav.js';
import {
    MISSING_SLUG_WARNING,
    filterQrCheckpoints,
    qrCheckpoints,
    qrJobs
} from '../qr/qr-batch.js';
import { qrPngDataUrl, qrSvg } from '../qr/qr-draw.js';

const PRINT_HINT = 'Aponte a câmera do celular para saber onde você está';

const state = {
    rows: [],
    query: '',
    selected: new Set(),
    perPage: '2'
};

document.addEventListener('DOMContentLoaded', () => {
    insertTopNav('admin');
    whenAdminGranted(start);
});

function start() {
    const app = document.getElementById('qr-app');
    if (!app) return;
    app.classList.remove('hidden');
    bind();
    load();
}

function bind() {
    const filter = document.getElementById('qr-filter');
    filter.addEventListener('input', () => {
        state.query = filter.value;
        render();
    });
    document.getElementById('qr-all').addEventListener('click', () => {
        visibleRows().forEach((row) => {
            if (!row.missingSlug) state.selected.add(row.key);
        });
        render();
    });
    document.getElementById('qr-none').addEventListener('click', () => {
        visibleRows().forEach((row) => state.selected.delete(row.key));
        render();
    });
    document.querySelectorAll('input[name="qr-per-page"]').forEach((input) => {
        input.addEventListener('change', () => {
            if (input.checked) state.perPage = input.value;
            const preview = document.getElementById('qr-preview');
            if (preview) preview.dataset.perPage = state.perPage;
        });
    });
    document.getElementById('qr-print').addEventListener('click', () => {
        window.print();
    });
    document.getElementById('qr-retry').addEventListener('click', load);
}

async function load() {
    const status = document.getElementById('qr-status');
    const retry = document.getElementById('qr-retry');
    status.textContent = 'Carregando checkpoints…';
    retry.hidden = true;
    try {
        const data = await getMap();
        const nodes = data && Array.isArray(data.nodes) ? data.nodes : [];
        state.rows = qrCheckpoints(nodes);
        state.selected = new Set(state.rows.filter((row) => !row.missingSlug).map((row) => row.key));
        status.textContent = '';
        render();
    } catch (err) {
        state.rows = [];
        state.selected.clear();
        status.textContent = err && err.message ? err.message : 'Não foi possível carregar os checkpoints.';
        retry.hidden = false;
        render();
    }
}

function visibleRows() {
    return filterQrCheckpoints(state.rows, state.query);
}

function render() {
    renderList();
    renderPreview();
}

function renderList() {
    const list = document.getElementById('qr-list');
    list.replaceChildren();
    const rows = visibleRows();
    if (!state.rows.length && !document.getElementById('qr-status').textContent) {
        const empty = document.createElement('li');
        empty.className = 'qr-empty';
        empty.textContent = 'Nenhum checkpoint para mostrar.';
        list.append(empty);
        return;
    }
    if (!rows.length) {
        const empty = document.createElement('li');
        empty.className = 'qr-empty';
        empty.textContent = 'Nenhum checkpoint com esse filtro.';
        list.append(empty);
        return;
    }
    rows.forEach((row) => {
        const item = document.createElement('li');
        if (row.missingSlug) {
            item.className = 'qr-missing';
            const warning = document.createElement('p');
            warning.className = 'qr-warning';
            const name = document.createElement('strong');
            name.textContent = row.name;
            warning.append(name, document.createTextNode(` — ${MISSING_SLUG_WARNING}`));
            item.append(warning);
            list.append(item);
            return;
        }
        const label = document.createElement('label');
        label.className = 'qr-choice';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.checked = state.selected.has(row.key);
        input.addEventListener('change', () => {
            if (input.checked) state.selected.add(row.key);
            else state.selected.delete(row.key);
            renderPreview();
        });
        const copy = document.createElement('span');
        copy.className = 'qr-choice-copy';
        const name = document.createElement('strong');
        name.textContent = row.name;
        const category = document.createElement('span');
        category.textContent = row.categoryLabel || 'Sem categoria';
        const slug = document.createElement('span');
        slug.className = 'mono qr-choice-slug';
        slug.textContent = row.slug;
        copy.append(name, category, slug);
        label.append(input, copy);
        item.append(label);
        list.append(item);
    });
}

function selectedRows() {
    return state.rows.filter((row) => state.selected.has(row.key));
}

function renderPreview() {
    const preview = document.getElementById('qr-preview');
    const summary = document.getElementById('qr-summary');
    const print = document.getElementById('qr-print');
    preview.dataset.perPage = state.perPage;
    preview.replaceChildren();
    const chosen = selectedRows();
    const { jobs, skipped } = qrJobs(chosen);
    const parts = [];
    parts.push(jobs.length === 1 ? '1 QR code' : `${jobs.length} QR codes`);
    if (skipped.length) {
        parts.push(skipped.length === 1
            ? `1 ${MISSING_SLUG_WARNING}`
            : `${skipped.length} ${MISSING_SLUG_WARNING}`);
    }
    summary.textContent = state.rows.length ? parts.join('. ') + '.' : '';
    print.disabled = jobs.length === 0;
    jobs.forEach((job, index) => preview.append(card(job, index)));
}

function card(job, index) {
    const article = document.createElement('article');
    article.className = 'qr-card';
    const mark = document.createElement('div');
    mark.className = 'qr-mark';
    const safe = String(index);
    mark.innerHTML = qrSvg(job.text, {
        title: `QR code de ${job.name}`,
        titleId: `qr-title-${safe}`,
        description: PRINT_HINT,
        descriptionId: `qr-desc-${safe}`
    });

    const name = document.createElement('h2');
    name.className = 'qr-name';
    name.textContent = job.name;

    const category = document.createElement('p');
    category.className = 'qr-category';
    category.textContent = job.categoryLabel || 'Sem categoria';

    const hint = document.createElement('p');
    hint.className = 'qr-hint';
    hint.textContent = PRINT_HINT;

    const slug = document.createElement('p');
    slug.className = 'qr-slug mono';
    slug.textContent = job.slug;

    const downloads = document.createElement('div');
    downloads.className = 'qr-downloads no-print';
    downloads.append(
        downloadButton(`Baixar PNG de ${job.name}`, 'PNG', () => downloadPng(job)),
        downloadButton(`Baixar SVG de ${job.name}`, 'SVG', () => downloadSvg(job, safe))
    );

    article.append(mark, name, category, hint, slug, downloads);
    return article;
}

function downloadButton(label, text, onClick) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn-secondary';
    button.textContent = text;
    button.setAttribute('aria-label', label);
    button.addEventListener('click', onClick);
    return button;
}

function fileBase(job) {
    const slug = String(job.slug || 'qr').trim().toLowerCase();
    const safe = slug.replace(/[^\p{L}\p{N}_-]+/gu, '-').replace(/^-|-$/g, '');
    return safe || 'qr';
}

function downloadPng(job) {
    const href = qrPngDataUrl(job.text);
    saveUrl(`${fileBase(job)}.png`, href);
}

function downloadSvg(job, index) {
    const svg = qrSvg(job.text, {
        title: `QR code de ${job.name}`,
        titleId: `qr-file-${index}`,
        description: PRINT_HINT,
        descriptionId: `qr-file-desc-${index}`
    });
    const blob = new Blob([svg], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    saveUrl(`${fileBase(job)}.svg`, url);
    setTimeout(() => URL.revokeObjectURL(url), 1500);
}

function saveUrl(filename, href) {
    const link = document.createElement('a');
    link.href = href;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
}
