/**
 * Tela única do visitante.
 * Máquina: E0 Inicial, E1 Câmera, E2 Busca, E3 Prévia, E4 Navegando,
 * E5 Chegada, e os erros de câmera, rota, mapa e rede.
 * E2 lista destinos na folha. E3 calcula a rota, desenha e libera "Iniciar rota".
 * E4 ainda é o stub da navegação (o passo a passo guiado entra na T7).
 */

import { loadDestinationCatalog } from './core/destination-catalog.js';
import {
    RESOLVE_UNRECOGNIZED,
    resolveScannedCheckpoint
} from './core/checkpoints.js';
import { checkpointAnchor } from './route/model.js';
import { mountCameraOverlay } from './ui/camera-overlay.js';
import { createQrButton } from './ui/qr-button.js';
import { mountRouteBar } from './ui/route-bar.js';
import { mountSearchSheet } from './ui/search-sheet.js';
import { mountMapView } from './map/map-view.js';
import { planRoute } from './nav/routing.js';
import { parseQr, parseScanLocation } from './qr/qr-format.js';
import {
    formatHash,
    hydrateSession,
    pointsFromHash,
    saveSession,
    toStored
} from './core/store.js';

export const State = Object.freeze({
    E0: 'E0',
    E1: 'E1',
    E2: 'E2',
    E3: 'E3',
    E4: 'E4',
    E5: 'E5',
    ERRO_CAMERA: 'ERRO_CAMERA',
    ERRO_ROTA: 'ERRO_ROTA',
    ERRO_MAPA: 'ERRO_MAPA',
    ERRO_REDE: 'ERRO_REDE'
});

const OVERLAYS = new Set([State.E1, State.E2]);
const ERRORS = new Set([State.ERRO_CAMERA, State.ERRO_ROTA, State.ERRO_MAPA, State.ERRO_REDE]);

const ERROR_TEXT = {
    [State.ERRO_CAMERA]: 'Não foi possível abrir a câmera.',
    [State.ERRO_ROTA]: 'Não encontramos um caminho entre esses pontos',
    [State.ERRO_MAPA]: 'Não foi possível carregar o mapa.',
    [State.ERRO_REDE]: 'Sem conexão com o servidor.'
};

const INSTRUCTION = {
    [State.E0]: 'Leia um QR para saber onde você está.',
    [State.E1]: 'Aponte para o QR code do ponto.',
    [State.E2]: 'Busca de destino aberta.',
    [State.E3]: 'Prévia da rota.',
    previewNotice: 'Leia um QR para saber onde você está',
    [State.E4]: 'Navegando até o destino.',
    [State.E5]: 'Você chegou ao destino.',
    [State.ERRO_CAMERA]: ERROR_TEXT[State.ERRO_CAMERA],
    [State.ERRO_ROTA]: ERROR_TEXT[State.ERRO_ROTA],
    [State.ERRO_MAPA]: ERROR_TEXT[State.ERRO_MAPA],
    [State.ERRO_REDE]: ERROR_TEXT[State.ERRO_REDE]
};

export function canStartRoute(session) {
    return Boolean(session && session.origin && session.origin.slug && session.destination && session.destination.slug);
}

/** A polilinha fica no mapa na prévia e enquanto a navegação (E4) não sai. */
export function showsRoute(state) {
    return state === State.E3 || state === State.E4;
}

function eventPoint(value) {
    if (!value) return null;
    if (typeof value === 'string') {
        const slug = value.trim();
        return slug ? { slug, label: slug } : null;
    }
    const slug = value.slug == null ? '' : String(value.slug).trim();
    if (!slug) return null;
    const label = value.label || value.name || slug;
    return { slug, label: String(label) };
}

function copySession(session) {
    const source = session || {};
    return {
        origin: source.origin ? { slug: source.origin.slug, label: source.origin.label || source.origin.slug } : null,
        destination: source.destination
            ? { slug: source.destination.slug, label: source.destination.label || source.destination.slug }
            : null,
        state: source.state || State.E0,
        returnTo: source.returnTo || null,
        cameraMessage: source.cameraMessage || null,
        announceOrigin: false
    };
}

function navigating(session) {
    if (!session) return false;
    return session.state === State.E4 || session.returnTo === State.E4;
}

function overlayReturn(session) {
    if (OVERLAYS.has(session.state)) return session.returnTo || State.E0;
    if (ERRORS.has(session.state)) return State.E0;
    return session.state;
}

/**
 * Transição pura. Não mexe no DOM nem no histórico.
 * E4 e E5 seguem stub. E3 já calcula a rota fora daqui.
 */
export function transition(session, event) {
    const current = copySession(session);
    const type = event && event.type;
    if (!type) return current;

    if (type === 'set-origin') return { ...current, origin: eventPoint(event.origin) };
    if (type === 'set-destination') return { ...current, destination: eventPoint(event.destination) };
    if (type === 'select-destination') {
        const destination = eventPoint(event.destination);
        if (!destination) return current;
        if (current.state === State.E4 || current.state === State.E5 || ERRORS.has(current.state)) return current;
        return { ...current, destination, state: State.E3, returnTo: null };
    }
    if (type === 'clear-origin') return { ...current, origin: null };
    if (type === 'clear-destination') return { ...current, destination: null };

    if (type === 'open-camera') {
        if (current.state === State.E1) return current;
        return { ...current, state: State.E1, returnTo: overlayReturn(current) };
    }
    if (type === 'open-search') {
        if (current.state === State.E2) return current;
        return { ...current, state: State.E2, returnTo: overlayReturn(current) };
    }
    if (type === 'qr-resolved') {
        const origin = eventPoint(event.origin);
        if (!origin) return current;
        if (navigating(current)) {
            return {
                ...current,
                origin,
                state: State.E4,
                returnTo: null,
                cameraMessage: null,
                announceOrigin: true
            };
        }
        const hasDestination = Boolean(current.destination && current.destination.slug);
        return {
            ...current,
            origin,
            state: hasDestination ? State.E3 : State.E0,
            returnTo: null,
            cameraMessage: null,
            announceOrigin: true
        };
    }
    if (type === 'back' || type === 'close-overlay') {
        if (OVERLAYS.has(current.state)) {
            return { ...current, state: current.returnTo || State.E0, returnTo: null };
        }
        if (current.state === State.ERRO_CAMERA && current.returnTo === State.E4) {
            return { ...current, state: State.E4, returnTo: null, cameraMessage: null };
        }
        if (current.state === State.E3 || current.state === State.E5 || ERRORS.has(current.state)) {
            return { ...current, state: State.E0, returnTo: null, cameraMessage: null };
        }
        if (current.state === State.E4) return { ...current, state: State.E3, returnTo: null };
        return current;
    }
    if (type === 'start-route') {
        if (!canStartRoute(current)) return current;
        if (OVERLAYS.has(current.state) || ERRORS.has(current.state) || current.state === State.E4) return current;
        if (current.state === State.E3) return { ...current, state: State.E4, returnTo: null };
        return { ...current, state: State.E3, returnTo: null };
    }
    if (type === 'confirm-preview') {
        if (current.state !== State.E3 || !canStartRoute(current)) return current;
        return { ...current, state: State.E4 };
    }
    if (type === 'arrive') {
        if (current.state !== State.E4) return current;
        return { ...current, state: State.E5 };
    }
    if (type === 'finish') {
        if (current.state !== State.E5) return current;
        return { ...current, state: State.E0 };
    }
    if (type === 'cancel-preview') {
        if (current.state !== State.E3) return current;
        return { ...current, state: State.E0, returnTo: null };
    }
    if (type === 'stop-navigation') {
        if (current.state !== State.E4) return current;
        return { ...current, state: State.E0, returnTo: null };
    }
    if (type === 'camera-error') {
        return {
            ...current,
            state: State.ERRO_CAMERA,
            returnTo: navigating(current) ? State.E4 : null,
            cameraMessage: event.message || ERROR_TEXT[State.ERRO_CAMERA]
        };
    }
    if (type === 'route-error') return { ...current, state: State.ERRO_ROTA, returnTo: null };
    if (type === 'map-error') return { ...current, state: State.ERRO_MAPA, returnTo: null };
    if (type === 'network-error') return { ...current, state: State.ERRO_REDE, returnTo: null };
    if (type === 'dismiss-error') {
        if (!ERRORS.has(current.state)) return current;
        if (current.state === State.ERRO_CAMERA && current.returnTo === State.E4) {
            return { ...current, state: State.E4, returnTo: null, cameraMessage: null };
        }
        return { ...current, state: State.E0, returnTo: null, cameraMessage: null };
    }
    if (type === 'retry') {
        if (current.state === State.ERRO_CAMERA) {
            return {
                ...current,
                state: State.E1,
                returnTo: current.returnTo === State.E4 ? State.E4 : State.E0,
                cameraMessage: null
            };
        }
        if (current.state === State.ERRO_ROTA) {
            return canStartRoute(current)
                ? { ...current, state: State.E3, returnTo: null }
                : { ...current, state: State.E0, returnTo: null };
        }
        if (current.state === State.ERRO_MAPA || current.state === State.ERRO_REDE) {
            return { ...current, state: State.E0, returnTo: null };
        }
        return current;
    }
    return current;
}

/** QR lido em E4 (ou com a câmera aberta por cima da navegação) recalibra sem cancelar a rota. */
export function shouldRecalibrate(session, event) {
    if (!event || event.type !== 'qr-resolved') return false;
    if (!eventPoint(event.origin)) return false;
    return navigating(session || {});
}

/** Evento `recalibrate` para a T7. `target` é `window` na página. */
export function emitRecalibrate(origin, target = globalThis) {
    const EventCtor = (target && target.CustomEvent) || globalThis.CustomEvent;
    if (!target || typeof target.dispatchEvent !== 'function' || typeof EventCtor !== 'function') return null;
    const event = new EventCtor('recalibrate', { detail: { origin } });
    target.dispatchEvent(event);
    return event;
}

/** `push` ao abrir folha/câmera, `back` ao fechar, `none` no resto. */
export function historyEffect(prevState, nextState) {
    const prev = prevState && prevState.state ? prevState.state : prevState;
    const next = nextState && nextState.state ? nextState.state : nextState;
    if (!OVERLAYS.has(prev) && OVERLAYS.has(next)) return 'push';
    if (OVERLAYS.has(prev) && next !== prev && !OVERLAYS.has(next)) return 'back';
    return 'none';
}

function pageUrl(session) {
    return `${location.pathname}${location.search}${formatHash(session)}`;
}

function sameUrl(session) {
    return `${location.pathname}${location.search}${location.hash}` === pageUrl(session);
}

let session = null;
let routeBar = null;
let searchSheet = null;
let camera = null;
let instructions = null;
let flow = null;
let searchField = null;
let mapView = null;
let mapReady = Promise.resolve(null);
let background = [];
let suppressPop = false;
let restoreSearchFocus = false;
let banner = null;
let pendingPin = null;
let scanRetry = null;
let focusCameraError = false;
let scanToken = 0;
let renderedState = null;
let routeResult = null;
let routeSignature = '';

function routeKey() {
    const origin = session && session.origin && session.origin.slug;
    const destination = session && session.destination && session.destination.slug;
    if (!origin || !destination) return '';
    return `${origin}>${destination}`;
}

function computeRouteForSession() {
    const key = routeKey();
    const drawing = Boolean(session) && showsRoute(session.state) && key;
    if (!drawing) {
        routeResult = null;
        routeSignature = '';
        return null;
    }
    if (!mapView || !mapView.model) return null;
    if (!routeResult || routeResult.key !== key) {
        const planned = planRoute({
            origin: session.origin.slug,
            destination: session.destination.slug,
            checkpoints: mapView.model.checkpoints,
            connections: mapView.model.connections || [],
            mapConfig: mapView.model.config
        });
        routeResult = { key, ...planned };
        if (!planned.ok) {
            const failedKey = key;
            const failedState = session.state;
            queueMicrotask(() => {
                if (!session || routeKey() !== failedKey || session.state !== failedState) return;
                if (session.state === State.E3 || session.state === State.E4) {
                    dispatch({ type: 'route-error' });
                }
            });
        }
    }
    return routeResult;
}

function instructionFor(current, summary) {
    if (summary && summary.announcement && (current.state === State.E3 || current.state === State.E4)) {
        return summary.announcement;
    }
    if (current.announceOrigin && current.origin && current.origin.label) {
        const where = `Você está em ${current.origin.label}`;
        if (current.state === State.E0 || current.state === State.E4) return where;
        const rest = INSTRUCTION[current.state];
        return rest ? `${where}. ${rest}` : where;
    }
    if (current.state === State.ERRO_CAMERA) {
        return current.cameraMessage || ERROR_TEXT[State.ERRO_CAMERA];
    }
    if (current.state === State.E3 && !(current.origin && current.origin.slug)) {
        return `${INSTRUCTION[State.E3]} ${INSTRUCTION.previewNotice}`;
    }
    if (current.state === State.E0 && (current.origin || current.destination)) {
        const origin = current.origin ? current.origin.label : 'sem origem';
        const destination = current.destination ? current.destination.label : 'sem destino';
        return `Origem ${origin}. Destino ${destination}.`;
    }
    return INSTRUCTION[current.state] || '';
}

function setInert(locked) {
    background.forEach((el) => {
        if (el) el.inert = locked;
    });
}

function render() {
    if (!routeBar) return;
    if (session.state === State.ERRO_CAMERA && renderedState !== State.ERRO_CAMERA) {
        focusCameraError = true;
    }
    renderedState = session.state;
    const planned = computeRouteForSession();
    const summary = planned && planned.ok && showsRoute(session.state) ? planned.route.summary : null;
    if (instructions) {
        instructions.setAttribute('aria-live', summary ? 'off' : 'polite');
        const text = instructionFor(session, summary);
        if (instructions.textContent !== text) instructions.textContent = text;
    }
    const shell = document.getElementById('visitor-shell');
    if (shell) shell.dataset.state = session.state;
    routeBar.update(session, {
        summary,
        canStart: session.state === State.E3 ? Boolean(planned && planned.ok) : undefined
    });
    if (searchField) {
        const label = session.destination
            ? `Destino atual: ${session.destination.label}. Para onde você quer ir?`
            : 'Para onde você quer ir?';
        searchField.value = session.destination ? session.destination.label : '';
        searchField.setAttribute('aria-label', label);
    }
    const overlay = OVERLAYS.has(session.state);
    setInert(overlay);
    if (searchSheet) searchSheet.setOpen(session.state === State.E2);
    if (camera) camera.setOpen(session.state === State.E1);
    const mapHost = document.getElementById('visitor-map');
    if (mapHost) {
        const where = session.origin && session.origin.label
            ? `Mapa do prédio. Você está em ${session.origin.label}`
            : 'Mapa do prédio';
        mapHost.setAttribute('aria-label', where);
    }
    renderFlow(planned);
    renderBanner();
    paintRoute(planned);
    if (session.state === State.ERRO_CAMERA && focusCameraError) {
        focusCameraError = false;
        const code = document.getElementById('camera-error-code');
        if (code && typeof code.focus === 'function') code.focus();
    }
}

function paintRoute(planned) {
    if (!mapView) return;
    const drawing = Boolean(planned && planned.ok && showsRoute(session.state));
    const destination = session.destination && session.destination.slug;
    if (typeof mapView.highlight === 'function') mapView.highlight(destination, { pan: !drawing });
    if (drawing) {
        mapView.showOrigin(null);
        const signature = `${routeKey()}|${session.state}`;
        const fit = routeSignature !== signature;
        routeSignature = signature;
        mapView.showRoute(planned.route, { fit });
        return;
    }
    if (typeof mapView.clearRoute === 'function') mapView.clearRoute();
    const slug = session.origin && session.origin.slug;
    const pin = pendingPin && pendingPin.slug === slug ? pendingPin.anchor : null;
    mapView.showOrigin(slug, pin);
}

function renderFlow(planned) {
    if (!flow) return;
    const keptCode = (flow.querySelector('#camera-error-code') || {}).value || '';
    if (session.state !== State.ERRO_CAMERA) flow.classList.remove('is-camera-error');
    flow.classList.remove('is-preview');
    flow.replaceChildren();
    const stub = session.state === State.E4 || session.state === State.E5;
    const preview = session.state === State.E3;
    const error = ERRORS.has(session.state);
    flow.hidden = !stub && !preview && !error;
    if (!stub && !preview && !error) return;

    const title = document.createElement('p');
    title.className = 'flow-title';
    if (preview) {
        flow.classList.add('is-preview');
        if (!(session.origin && session.origin.slug)) {
            title.textContent = 'Prévia da rota';
            const notice = document.createElement('p');
            notice.className = 'flow-notice';
            notice.id = 'preview-origin-notice';
            notice.textContent = INSTRUCTION.previewNotice;
            flow.append(title, notice, flowButton('Voltar da prévia', 'Voltar', 'cancel-preview'));
            return;
        }
        if (!planned || !planned.ok) {
            flow.hidden = true;
            return;
        }
        flow.append(stepsPanel(planned.route), flowButton('Voltar da prévia', 'Voltar', 'cancel-preview'));
        return;
    }
    if (session.state === State.E4) {
        // TODO: E4 Navegando — o passo a passo guiado entra na T7.
        title.textContent = 'Navegando';
        flow.append(title, flowButton('Cheguei ao destino', 'Cheguei', 'arrive'), flowButton('Encerrar navegação', 'Encerrar', 'stop-navigation'));
        return;
    }
    if (session.state === State.E5) {
        // TODO: E5 Chegada — encerrar a rota no destino.
        title.textContent = 'Você chegou';
        flow.append(title, flowButton('Concluir rota', 'Concluir', 'finish'));
        return;
    }
    if (session.state === State.ERRO_CAMERA) {
        title.textContent = session.cameraMessage || ERROR_TEXT[State.ERRO_CAMERA];
        flow.append(title, cameraErrorForm(keptCode), flowButton('Voltar ao mapa', 'Voltar', 'dismiss-error'), flowButton('Tentar de novo', 'Tentar de novo', 'retry'));
        flow.classList.add('is-camera-error');
        return;
    }
    if (session.state === State.ERRO_ROTA) {
        title.textContent = ERROR_TEXT[State.ERRO_ROTA];
        const change = flowButton('Trocar destino', 'Trocar destino', 'open-search');
        change.classList.remove('btn-secondary');
        change.classList.add('btn-primary');
        flow.append(title, change);
        return;
    }
    flow.classList.remove('is-camera-error');
    title.textContent = ERROR_TEXT[session.state] || 'Algo deu errado.';
    flow.append(title, flowButton('Voltar ao mapa', 'Voltar', 'dismiss-error'), flowButton('Tentar de novo', 'Tentar de novo', 'retry'));
}

function stepsPanel(route) {
    const section = document.createElement('section');
    section.className = 'route-steps';
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'route-steps-toggle';
    toggle.setAttribute('aria-expanded', 'true');
    toggle.setAttribute('aria-controls', 'route-step-list');
    toggle.textContent = 'Passos da rota';
    const list = document.createElement('ol');
    list.id = 'route-step-list';
    list.className = 'route-step-list';
    list.setAttribute('aria-label', 'Passos da rota');
    const steps = route && Array.isArray(route.steps) ? route.steps : [];
    if (!steps.length) {
        const item = document.createElement('li');
        item.textContent = 'Você já está neste ponto';
        list.append(item);
    } else {
        steps.forEach((step) => {
            const item = document.createElement('li');
            item.textContent = step.text;
            list.append(item);
        });
    }
    toggle.addEventListener('click', () => {
        const open = toggle.getAttribute('aria-expanded') === 'true';
        toggle.setAttribute('aria-expanded', open ? 'false' : 'true');
        list.hidden = open;
    });
    section.append(toggle, list);
    return section;
}

function cameraErrorForm(kept) {
    const form = document.createElement('form');
    form.className = 'camera-error-form';
    const label = document.createElement('label');
    label.setAttribute('for', 'camera-error-code');
    label.textContent = 'Código do ponto';
    const input = document.createElement('input');
    input.id = 'camera-error-code';
    input.className = 'text-field';
    input.type = 'text';
    input.autocomplete = 'off';
    input.autocapitalize = 'off';
    input.spellcheck = false;
    input.placeholder = 'Código do ponto';
    input.setAttribute('aria-label', 'Código do ponto');
    input.value = kept;
    const submit = document.createElement('button');
    submit.type = 'submit';
    submit.className = 'btn btn-primary';
    submit.textContent = 'Usar este código';
    submit.setAttribute('aria-label', 'Usar este código');
    form.append(label, input, submit);
    form.addEventListener('submit', (event) => {
        event.preventDefault();
        submitManual(input.value);
    });
    return form;
}

function renderBanner() {
    if (!banner) return;
    if (session.state === State.E1 || !scanRetry) {
        banner.hidden = true;
        banner.replaceChildren();
        return;
    }
    banner.hidden = false;
    banner.replaceChildren();
    const text = document.createElement('p');
    text.textContent = scanRetry.message;
    banner.append(text);
    if (scanRetry.retry) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-secondary';
        button.textContent = 'Tentar de novo';
        button.setAttribute('aria-label', 'Tentar de novo');
        const run = scanRetry.retry;
        button.addEventListener('click', () => run());
        banner.append(button);
    }
}

function flowButton(label, text, type) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn-secondary';
    button.textContent = text;
    button.setAttribute('aria-label', label);
    button.addEventListener('click', () => dispatch({ type }));
    return button;
}

function commit(next, source, event) {
    const previous = session;
    const recalibrate = shouldRecalibrate(previous, event);
    const effect = historyEffect(session, next);
    const closingSearch = session && session.state === State.E2 && next.state !== State.E2;
    session = next;
    saveSession(toStored(session));
    if (recalibrate) emitRecalibrate(session.origin);
    if (source !== 'pop') {
        if (effect === 'push') {
            history.pushState({ povOverlay: session.state }, '', pageUrl(session));
        } else if (effect === 'back' && history.state && history.state.povOverlay) {
            restoreSearchFocus = closingSearch;
            suppressPop = true;
            render();
            history.back();
            return;
        } else if (!sameUrl(session)) {
            history.replaceState(history.state, '', pageUrl(session));
        }
    }
    render();
}

export function dispatch(event) {
    commit(transition(session, event), 'ui', event);
}

function requestBack() {
    if ((session.state === State.E1 || session.state === State.E2) && history.state && history.state.povOverlay) {
        history.back();
        return;
    }
    dispatch({ type: 'back' });
}

function onPopState() {
    if (suppressPop) {
        suppressPop = false;
        if (!sameUrl(session)) history.replaceState(history.state, '', pageUrl(session));
        render();
        if (restoreSearchFocus && searchField && typeof searchField.focus === 'function') searchField.focus();
        restoreSearchFocus = false;
        return;
    }
    let next = pointsFromHash(session, location.hash);
    if (OVERLAYS.has(session.state)) next = transition(next, { type: 'back' });
    commit(next, 'pop');
}

function placeRoleChrome() {
    const slot = document.getElementById('visitor-chrome');
    const bar = document.querySelector('[data-role-chrome]');
    if (slot && bar && bar.parentElement !== slot) slot.prepend(bar);
    return slot;
}

function openCamera() {
    dispatch({ type: 'open-camera' });
}

function openSearch() {
    dispatch({ type: 'open-search' });
}

function vibrateRead() {
    try {
        if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') navigator.vibrate(80);
    } catch (_) {
        /* o aparelho pode recusar a vibração */
    }
}

function rememberPin(found) {
    if (!found) return;
    const anchor = checkpointAnchor(found);
    pendingPin = anchor ? { slug: found.slug, anchor } : { slug: found.slug, anchor: null };
    if (mapView) mapView.showOrigin(found.slug, anchor);
}

async function checkpointList() {
    try {
        await mapReady;
    } catch (_) {
        /* o mapa segue sem a lista */
    }
    const loaded = mapView && mapView.model && Array.isArray(mapView.model.checkpoints)
        ? mapView.model.checkpoints
        : null;
    if (loaded && loaded.length) return loaded;
    try {
        const catalog = await loadDestinationCatalog();
        return (catalog && catalog.checkpoints) || loaded || [];
    } catch (_) {
        return loaded || [];
    }
}

function showProblem(message, retry) {
    scanRetry = { message, retry: retry || null };
    if (session && session.state === State.E1 && camera) {
        camera.setStatus(message, retry ? { retry } : {});
        return;
    }
    renderBanner();
}

async function settleScan(parsed) {
    const token = ++scanToken;
    if (!parsed || parsed.error || !parsed.cp) {
        return parsed && parsed.error === 'unsupported-version' ? 'unsupported' : 'invalid';
    }
    try {
        const found = await resolveScannedCheckpoint({
            b: parsed.b,
            cp: parsed.cp,
            checkpoints: mapView && mapView.model ? mapView.model.checkpoints : null,
            loadCheckpoints: checkpointList
        });
        if (token !== scanToken) return 'stale';
        rememberPin(found);
        scanRetry = null;
        dispatch({
            type: 'qr-resolved',
            origin: { slug: found.slug, label: found.name || found.slug }
        });
        return 'ok';
    } catch (err) {
        if (token !== scanToken) return 'stale';
        if (err && err.code === 'not-found') return 'not-found';
        return 'network';
    }
}

async function onCameraSubmit(text, source) {
    const parsed = parseQr(text);
    if (source === 'camera' && parsed && !parsed.error) vibrateRead();
    const result = await settleScan(parsed);
    if (result === 'ok' || result === 'stale') return result;
    if (session.state === State.E1) return result;
    if (result === 'not-found') showProblem(RESOLVE_UNRECOGNIZED);
    else if (result === 'network') showProblem('Tentar de novo', () => onCameraSubmit(text, source));
    else if (result === 'unsupported') showProblem('Versão do QR não suportada.');
    else showProblem('Este QR não é de um ponto.');
    return result;
}

function submitManual(text) {
    return onCameraSubmit(text, 'manual');
}

async function applyDeepLink(parsed) {
    const result = await settleScan(parsed);
    if (result === 'ok' || result === 'stale') return;
    if (result === 'not-found') showProblem(RESOLVE_UNRECOGNIZED);
    else if (result === 'network') showProblem('Tentar de novo', () => applyDeepLink(parsed));
    else if (result === 'unsupported') showProblem('Versão do QR não suportada.');
    else showProblem('Este QR não é de um ponto.');
}

export function mountVisitorApp() {
    const shell = document.getElementById('visitor-shell');
    if (!shell || shell.dataset.mounted === 'true') return;
    shell.dataset.mounted = 'true';

    instructions = document.getElementById('visitor-instructions');
    searchField = document.getElementById('search-field');
    flow = document.getElementById('visitor-flow');
    background = [
        document.querySelector('.visitor-top'),
        document.querySelector('.visitor-map'),
        document.querySelector('.visitor-bottom')
    ];

    placeRoleChrome();
    banner = document.createElement('div');
    banner.id = 'scan-banner';
    banner.className = 'scan-banner';
    banner.hidden = true;
    banner.setAttribute('role', 'alert');
    const top = document.querySelector('.visitor-top');
    if (top) top.append(banner);

    const slot = document.getElementById('visitor-chrome');
    if (slot && !slot.querySelector('.qr-button')) {
        slot.append(createQrButton({ onClick: openCamera }));
    }

    routeBar = mountRouteBar(document.getElementById('route-bar'), {
        onOrigin: openCamera,
        onDestination: openSearch,
        onStart: () => dispatch({ type: 'start-route' })
    });
    searchSheet = mountSearchSheet(document.getElementById('search-sheet-root'), {
        onClose: requestBack,
        onSelect: (item) => dispatch({
            type: 'select-destination',
            destination: { slug: item.slug, label: item.name || item.slug }
        }),
        loadCatalog: () => loadDestinationCatalog(),
        originSlug: () => (session && session.origin && session.origin.slug) || ''
    });
    camera = mountCameraOverlay(document.getElementById('camera-root'), {
        onClose: requestBack,
        onSubmit: (text, source) => onCameraSubmit(text, source),
        onCameraFailure: ({ message }) => dispatch({ type: 'camera-error', message })
    });

    const pendingScan = parseScanLocation(location.hash);
    session = {
        ...hydrateSession(location.hash),
        returnTo: null,
        cameraMessage: null,
        announceOrigin: false
    };
    if (pendingScan && (session.state === State.E1 || session.state === State.ERRO_CAMERA)) {
        session.state = session.destination && session.destination.slug ? State.E3 : State.E0;
    }
    saveSession(toStored(session));
    if (OVERLAYS.has(session.state)) {
        session.returnTo = State.E0;
        history.replaceState({}, '', pageUrl(session));
        history.pushState({ povOverlay: session.state }, '', pageUrl(session));
    } else if (!pendingScan && !sameUrl(session)) {
        history.replaceState(history.state, '', pageUrl(session));
    }

    if (searchField) {
        searchField.addEventListener('click', openSearch);
        searchField.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                openSearch();
            }
        });
    }

    window.addEventListener('popstate', onPopState);
    window.addEventListener('hashchange', () => {
        const scan = parseScanLocation(location.hash);
        if (scan) applyDeepLink(scan);
    });
    render();
    if (pendingScan) applyDeepLink(pendingScan);

    const mapHost = document.getElementById('visitor-map');
    if (mapHost) {
        mapReady = mountMapView(mapHost).then((view) => {
            mapView = view;
            render();
            return view;
        }).catch(() => null);
    }
}

if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', () => {
        if (document.body && document.body.dataset.app === 'visitor') mountVisitorApp();
    });
}
