/**
 * Folha inferior da busca (E2). O único campo editável da tela fica aqui,
 * já focado, para o teclado do celular subir junto com a folha.
 */

import { focusableElements, trapTabKey } from './focus-trap.js';
import { lucideIcon } from './icons.js';
import {
    ALL_CHIP,
    SEARCH_DEBOUNCE_MS,
    buildDestinationCatalog,
    debounce,
    destinationCountLabel,
    searchDestinations
} from '../core/search.js';

export function mountSearchSheet(root, { onClose, onSelect, loadCatalog, originSlug } = {} as any) {
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

    const queryInput = document.createElement('input');
    queryInput.id = 'destination-query';
    queryInput.className = 'text-field destination-query';
    queryInput.type = 'text';
    queryInput.inputMode = 'search';
    queryInput.enterKeyHint = 'search';
    queryInput.autocomplete = 'off';
    queryInput.autocapitalize = 'off';
    queryInput.spellcheck = false;
    queryInput.placeholder = 'Para onde você quer ir?';
    queryInput.setAttribute('aria-label', 'Para onde você quer ir?');
    queryInput.setAttribute('role', 'combobox');
    queryInput.setAttribute('aria-autocomplete', 'list');
    queryInput.setAttribute('aria-expanded', 'false');
    queryInput.setAttribute('aria-controls', 'destination-list');
    queryInput.setAttribute('aria-activedescendant', '');

    const chipsEl = document.createElement('div');
    chipsEl.className = 'category-chips';
    chipsEl.setAttribute('role', 'group');
    chipsEl.setAttribute('aria-label', 'Categorias');
    chipsEl.hidden = true;

    const countEl = document.createElement('p');
    countEl.className = 'destination-count';
    countEl.setAttribute('aria-live', 'polite');
    countEl.setAttribute('aria-atomic', 'true');

    const body = document.createElement('div');
    body.className = 'sheet-body';

    sheet.append(handle, head, queryInput, chipsEl, countEl, body);
    root.replaceChildren(scrim, sheet);

    let open = false;
    let dragStart = 0;
    let dragging = false;
    let status = 'idle';
    let loadToken = 0;
    let checkpoints = [];
    let categories = null;
    let pxPerM = null;
    let query = '';
    let chip = ALL_CHIP;
    let activeIndex = 0;
    let visible = [];
    let chipSignature = '';

    const applyQuery = debounce((value) => {
        query = value;
        activeIndex = 0;
        renderResults();
    }, SEARCH_DEBOUNCE_MS);

    function currentOrigin() {
        if (typeof originSlug === 'function') return originSlug() || '';
        return originSlug || '';
    }

    function requestClose() {
        if (typeof onClose === 'function') onClose();
    }

    function choose(item) {
        if (item && typeof onSelect === 'function') onSelect(item);
    }

    function chooseActive() {
        if (!visible.length) return;
        const index = activeIndex >= 0 && activeIndex < visible.length ? activeIndex : 0;
        choose(visible[index]);
    }

    function focusField() {
        const field = document.getElementById('search-field');
        if (field && typeof field.focus === 'function') field.focus();
    }

    function focusQuery() {
        if (typeof queryInput.focus === 'function') queryInput.focus();
    }

    function resetFilters() {
        applyQuery.cancel();
        query = '';
        chip = ALL_CHIP;
        activeIndex = 0;
        queryInput.value = '';
    }

    function onKey(event) {
        if (!open) return;
        if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            requestClose();
            return;
        }
        if (document.activeElement === queryInput) {
            const options = body.querySelectorAll('[role="option"]');
            if (event.key === 'ArrowDown' && options.length) {
                event.preventDefault();
                moveActive(activeIndex < 0 ? 0 : activeIndex + 1);
                return;
            }
            if (event.key === 'ArrowUp' && options.length) {
                event.preventDefault();
                moveActive(activeIndex < 0 ? 0 : activeIndex - 1);
                return;
            }
            if (event.key === 'Home' && options.length) {
                event.preventDefault();
                moveActive(0);
                return;
            }
            if (event.key === 'End' && options.length) {
                event.preventDefault();
                moveActive(options.length - 1);
                return;
            }
            if (event.key === 'Enter') {
                event.preventDefault();
                applyQuery.cancel();
                const nextQuery = queryInput.value;
                if (nextQuery !== query) activeIndex = 0;
                query = nextQuery;
                renderResults();
                chooseActive();
                return;
            }
        }
        trapTabKey(sheet, event);
    }

    function moveActive(nextIndex) {
        const options = body.querySelectorAll('[role="option"]');
        if (!options.length) return;
        const index = Math.max(0, Math.min(options.length - 1, nextIndex));
        activeIndex = index;
        options.forEach((option, i) => {
            option.setAttribute('aria-selected', i === index ? 'true' : 'false');
        });
        const active = options[index];
        queryInput.setAttribute('aria-activedescendant', active.id);
        if (typeof active.scrollIntoView === 'function') active.scrollIntoView({ block: 'nearest' });
    }

    function chipButton(code, label) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'chip';
        button.dataset.chip = code;
        button.textContent = label;
        button.setAttribute('aria-pressed', code === chip ? 'true' : 'false');
        button.addEventListener('click', () => {
            chip = code;
            activeIndex = 0;
            syncChips();
            renderResults();
            focusQuery();
        });
        return button;
    }

    function syncChips() {
        chipsEl.querySelectorAll('[data-chip]').forEach((button: any) => {
            const on = button.dataset.chip === chip;
            button.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
    }

    function renderChipButtons(rows) {
        const signature = rows.map((row) => `${row.code}:${row.name}`).join('|');
        if (signature !== chipSignature) {
            chipSignature = signature;
            chipsEl.replaceChildren(
                chipButton(ALL_CHIP, 'Todos'),
                ...rows.map((row) => chipButton(row.code, row.name))
            );
        }
        syncChips();
    }

    function messageBlock(text, action) {
        const wrap = document.createElement('div');
        wrap.className = 'sheet-message';
        const paragraph = document.createElement('p');
        paragraph.textContent = text;
        wrap.append(paragraph);
        if (action) wrap.append(action);
        return wrap;
    }

    function clearButton() {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-secondary';
        button.textContent = 'Limpar busca';
        button.addEventListener('click', () => {
            resetFilters();
            renderResults();
            focusQuery();
        });
        return button;
    }

    function retryButton() {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-secondary';
        button.textContent = 'Tentar de novo';
        button.addEventListener('click', () => {
            reload();
            focusQuery();
        });
        return button;
    }

    function renderList(results) {
        const list = document.createElement('div');
        list.id = 'destination-list';
        list.className = 'destination-list';
        list.setAttribute('role', 'listbox');
        list.setAttribute('aria-label', 'Destinos');
        if (activeIndex >= results.length) activeIndex = 0;
        results.forEach((item, index) => {
            const option = document.createElement('div');
            option.className = 'destination-option';
            option.id = `destination-option-${index}`;
            option.setAttribute('role', 'option');
            option.setAttribute('aria-selected', index === activeIndex ? 'true' : 'false');
            option.dataset.slug = item.slug;
            option.tabIndex = -1;

            const copy = document.createElement('span');
            copy.className = 'destination-copy';
            const name = document.createElement('span');
            name.className = 'destination-name';
            name.textContent = item.name;
            const category = document.createElement('span');
            category.className = 'destination-category';
            const icon = lucideIcon(item.icon);
            if (icon) category.append(icon);
            const categoryName = document.createElement('span');
            categoryName.textContent = item.categoryName;
            category.append(categoryName);
            copy.append(name, category);
            option.append(copy);

            if (item.distanceLabel) {
                const distance = document.createElement('span');
                distance.className = 'destination-distance';
                distance.textContent = item.distanceLabel;
                option.append(distance);
            }

            option.addEventListener('click', () => choose(item));
            list.append(option);
        });
        const active = list.children[activeIndex];
        queryInput.setAttribute('aria-activedescendant', active ? active.id : '');
        return list;
    }

    function renderResults() {
        const catalog = buildDestinationCatalog(checkpoints, categories);
        if (status === 'ready' && catalog.showChips) {
            chipsEl.hidden = false;
            renderChipButtons(catalog.categories);
        } else {
            chipsEl.hidden = true;
            if (status !== 'ready') chipSignature = '';
        }

        if (status === 'loading') {
            visible = [];
            countEl.textContent = 'Carregando destinos…';
            queryInput.setAttribute('aria-activedescendant', '');
            body.replaceChildren(messageBlock('Carregando destinos…', retryButton()));
            return;
        }
        if (status === 'error') {
            visible = [];
            countEl.textContent = 'Não foi possível carregar os destinos.';
            queryInput.setAttribute('aria-activedescendant', '');
            body.replaceChildren(messageBlock('Não foi possível carregar os destinos.', retryButton()));
            return;
        }

        visible = searchDestinations(catalog.items, {
            query,
            chip,
            originSlug: currentOrigin(),
            pxPerM
        });
        countEl.textContent = destinationCountLabel(visible.length);
        if (!visible.length) {
            queryInput.setAttribute('aria-activedescendant', '');
            body.replaceChildren(messageBlock('Nenhum destino encontrado', clearButton()));
            return;
        }
        body.replaceChildren(renderList(visible));
    }

    async function reload() {
        const request = ++loadToken;
        status = 'loading';
        sheet.setAttribute('aria-busy', 'true');
        renderResults();
        try {
            if (typeof loadCatalog !== 'function') throw new Error('Sem catálogo.');
            const payload = await loadCatalog();
            if (request !== loadToken) return;
            checkpoints = payload && Array.isArray(payload.checkpoints) ? payload.checkpoints : [];
            categories = payload ? payload.categories : null;
            pxPerM = payload ? payload.pxPerM : null;
            status = 'ready';
        } catch (_) {
            if (request !== loadToken) return;
            checkpoints = [];
            categories = null;
            pxPerM = null;
            status = 'error';
        }
        if (request !== loadToken) return;
        sheet.setAttribute('aria-busy', 'false');
        activeIndex = 0;
        renderResults();
    }

    function setOpen(next) {
        const show = Boolean(next);
        queryInput.setAttribute('aria-expanded', show ? 'true' : 'false');
        if (show === open) {
            if (show) focusQuery();
            return;
        }
        open = show;
        scrim.hidden = !show;
        sheet.hidden = !show;
        sheet.style.transform = '';
        if (show) {
            document.addEventListener('keydown', onKey, true);
            resetFilters();
            if (status === 'idle' || status === 'error') reload();
            else renderResults();
            focusQuery();
        } else {
            document.removeEventListener('keydown', onKey, true);
            focusField();
        }
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

    queryInput.addEventListener('input', () => {
        applyQuery(queryInput.value);
    });

    return {
        setOpen,
        isOpen: () => open,
        element: sheet,
        reload
    };
}
