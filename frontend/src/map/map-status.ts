/** Aviso do mapa: carregando, planta ausente ou falha, com tentativa de novo. */

const PLANT_PENDING = 'A planta aparece quando o mapa estiver disponível.';

export function floorNotice(model, planError = '') {
    const failures = model && Array.isArray(model.problems)
        ? model.problems.filter(Boolean)
        : [];
    const imageError = planError ? String(planError) : '';
    const message = [...new Set([imageError, ...failures].filter(Boolean))].join(' ');
    if (message) {
        return {
            message,
            error: true,
            retry: true
        };
    }
    if (!model || !model.config || !model.config.plan_image) {
        return { message: PLANT_PENDING, error: false, retry: false };
    }
    return { message: '', error: false, retry: false };
}

export function mountMapStatus(anchor) {
    const box = document.createElement('div');
    box.className = 'map-status';
    box.setAttribute('role', 'status');
    box.setAttribute('aria-live', 'polite');
    box.hidden = true;

    const text = document.createElement('span');
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.className = 'btn btn-secondary map-status-retry';
    retry.textContent = 'Tentar de novo';
    retry.hidden = true;
    box.append(text, retry);
    if (anchor) anchor.append(box);

    let onRetry = null;
    const onClick = () => {
        if (typeof onRetry === 'function') onRetry();
    };
    retry.addEventListener('click', onClick);

    function setBusy(host, busy) {
        if (!host || typeof host.setAttribute !== 'function') return;
        if (busy) host.setAttribute('aria-busy', 'true');
        else host.removeAttribute('aria-busy');
    }

    return {
        show(message, { busy = false, error = false, onRetry: nextRetry = null, host = null } = {} as any) {
            const visible = Boolean(message);
            text.textContent = message || '';
            box.hidden = !visible;
            box.classList.toggle('is-error', Boolean(error) && visible);
            box.classList.toggle('is-busy', Boolean(busy) && visible);
            const canRetry = visible && typeof nextRetry === 'function';
            retry.hidden = !canRetry;
            onRetry = canRetry ? nextRetry : null;
            setBusy(host, Boolean(busy) && visible);
        },
        destroy() {
            retry.removeEventListener('click', onClick);
            onRetry = null;
            box.remove();
        }
    };
}
