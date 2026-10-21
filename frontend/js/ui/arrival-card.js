/**
 * Cartão da chegada (E5): nome do destino, novo destino e fim.
 */

export function mountArrivalCard(root, { onNewDestination, onFinish } = {}) {
    const card = document.createElement('section');
    card.className = 'arrival-card';
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-modal', 'false');
    card.setAttribute('aria-labelledby', 'arrival-title');
    card.hidden = true;

    const title = document.createElement('h2');
    title.id = 'arrival-title';
    title.className = 'arrival-title';
    title.tabIndex = -1;

    const actions = document.createElement('div');
    actions.className = 'arrival-actions';

    const again = document.createElement('button');
    again.type = 'button';
    again.className = 'btn btn-primary';
    again.textContent = 'Novo destino';
    again.setAttribute('aria-label', 'Novo destino');

    const done = document.createElement('button');
    done.type = 'button';
    done.className = 'btn btn-secondary';
    done.textContent = 'Fim';
    done.setAttribute('aria-label', 'Fim');

    actions.append(again, done);
    card.append(title, actions);
    root.append(card);

    again.addEventListener('click', () => {
        if (typeof onNewDestination === 'function') onNewDestination();
    });
    done.addEventListener('click', () => {
        if (typeof onFinish === 'function') onFinish();
    });

    function show(name) {
        const place = name || 'o destino';
        const text = `Você chegou a ${place}`;
        const open = !card.hidden && title.textContent === text;
        title.textContent = text;
        card.hidden = false;
        if (!open && typeof title.focus === 'function') title.focus();
    }

    function hide() {
        card.hidden = true;
    }

    return { show, hide, element: card };
}
