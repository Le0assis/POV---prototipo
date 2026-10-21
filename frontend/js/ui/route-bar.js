/**
 * Barra de rota do visitante. Sem campo de texto.
 * Sem origem e sem destino, fica o convite compacto do QR.
 */

export function mountRouteBar(root, { onOrigin, onDestination, onStart } = {}) {
    const compact = document.createElement('button');
    compact.type = 'button';
    compact.className = 'route-compact';
    compact.textContent = 'Leia um QR para saber onde você está';
    compact.setAttribute('aria-label', 'Leia um QR para saber onde você está');

    const expanded = document.createElement('div');
    expanded.className = 'route-expanded';

    const origin = document.createElement('button');
    origin.type = 'button';
    origin.className = 'route-point';
    const originKicker = document.createElement('span');
    originKicker.className = 'route-kicker';
    originKicker.textContent = 'Origem';
    const originValue = document.createElement('span');
    originValue.className = 'route-value';
    origin.append(originKicker, originValue);

    const destination = document.createElement('button');
    destination.type = 'button';
    destination.className = 'route-point';
    const destinationKicker = document.createElement('span');
    destinationKicker.className = 'route-kicker';
    destinationKicker.textContent = 'Destino';
    const destinationValue = document.createElement('span');
    destinationValue.className = 'route-value';
    destination.append(destinationKicker, destinationValue);

    const points = document.createElement('div');
    points.className = 'route-points';
    points.append(origin, destination);

    const start = document.createElement('button');
    start.type = 'button';
    start.className = 'btn btn-primary route-start';
    start.textContent = 'Iniciar rota';
    start.setAttribute('aria-label', 'Iniciar rota');

    expanded.append(points, start);
    root.replaceChildren(compact, expanded);

    compact.addEventListener('click', () => {
        if (typeof onOrigin === 'function') onOrigin();
    });
    origin.addEventListener('click', () => {
        if (typeof onOrigin === 'function') onOrigin();
    });
    destination.addEventListener('click', () => {
        if (typeof onDestination === 'function') onDestination();
    });
    start.addEventListener('click', () => {
        if (start.disabled) return;
        if (typeof onStart === 'function') onStart();
    });

    function update(session) {
        const current = session || {};
        const hasOrigin = Boolean(current.origin && current.origin.slug);
        const hasDestination = Boolean(current.destination && current.destination.slug);
        const compactMode = !hasOrigin && !hasDestination;
        compact.hidden = !compactMode;
        expanded.hidden = compactMode;

        const originLabel = hasOrigin ? `${current.origin.label} (QR)` : 'Toque para ler o QR';
        const destinationLabel = hasDestination ? current.destination.label : 'Toque para buscar';
        originKicker.textContent = hasOrigin ? 'Origem:' : 'Origem';
        originValue.textContent = originLabel;
        destinationValue.textContent = destinationLabel;
        origin.classList.toggle('is-empty', !hasOrigin);
        destination.classList.toggle('is-empty', !hasDestination);
        origin.setAttribute(
            'aria-label',
            hasOrigin
                ? `Origem: ${current.origin.label} (QR). Toque para ler o QR.`
                : 'Origem. Toque para ler o QR.'
        );
        destination.setAttribute(
            'aria-label',
            hasDestination
                ? `Destino: ${current.destination.label}. Toque para buscar.`
                : 'Destino. Toque para buscar.'
        );

        const ready = hasOrigin && hasDestination;
        start.disabled = !ready;
        start.setAttribute('aria-disabled', ready ? 'false' : 'true');
    }

    update({ origin: null, destination: null });
    return { update };
}
