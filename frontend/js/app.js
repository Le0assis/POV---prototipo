/**
 * Tela única do visitante.
 * Máquina: E0 Inicial, E1 Câmera, E2 Busca, E3 Prévia, E4 Navegando,
 * E5 Chegada, e os erros de câmera, rota, mapa e rede.
 * Nesta tarefa a interface visível é E0, E1 (espaço reservado) e E2 (folha vazia).
 */

import { mountCameraOverlay } from './ui/camera-overlay.js';
import { createQrButton } from './ui/qr-button.js';
import { mountRouteBar } from './ui/route-bar.js';
import { mountSearchSheet } from './ui/search-sheet.js';
import { mountMapView } from './map/map-view.js';
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
    [State.ERRO_ROTA]: 'Não foi possível montar a rota.',
    [State.ERRO_MAPA]: 'Não foi possível carregar o mapa.',
    [State.ERRO_REDE]: 'Sem conexão com o servidor.'
};

const INSTRUCTION = {
    [State.E0]: 'Leia um QR para saber onde você está.',
    [State.E1]: 'Câmera aberta. A leitura do QR ainda é um espaço reservado.',
    [State.E2]: 'Busca de destino aberta.',
    [State.E3]: 'Prévia da rota.',
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
        returnTo: source.returnTo || null
    };
}

function overlayReturn(session) {
    if (OVERLAYS.has(session.state)) return session.returnTo || State.E0;
    if (ERRORS.has(session.state)) return State.E0;
    return session.state;
}

/**
 * Transição pura. Não mexe no DOM nem no histórico.
 * E3–E5 existem aqui; a tela delas ainda é um stub.
 */
export function transition(session, event) {
    const current = copySession(session);
    const type = event && event.type;
    if (!type) return current;

    if (type === 'set-origin') return { ...current, origin: eventPoint(event.origin) };
    if (type === 'set-destination') return { ...current, destination: eventPoint(event.destination) };
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
    if (type === 'back' || type === 'close-overlay') {
        if (OVERLAYS.has(current.state)) {
            return { ...current, state: current.returnTo || State.E0, returnTo: null };
        }
        if (current.state === State.E3 || current.state === State.E5 || ERRORS.has(current.state)) {
            return { ...current, state: State.E0, returnTo: null };
        }
        if (current.state === State.E4) return { ...current, state: State.E3, returnTo: null };
        return current;
    }
    if (type === 'start-route') {
        if (!canStartRoute(current)) return current;
        if (OVERLAYS.has(current.state) || ERRORS.has(current.state) || current.state === State.E4) return current;
        return { ...current, state: State.E3, returnTo: null };
    }
    if (type === 'confirm-preview') {
        if (current.state !== State.E3) return current;
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
    if (type === 'camera-error') return { ...current, state: State.ERRO_CAMERA, returnTo: null };
    if (type === 'route-error') return { ...current, state: State.ERRO_ROTA, returnTo: null };
    if (type === 'map-error') return { ...current, state: State.ERRO_MAPA, returnTo: null };
    if (type === 'network-error') return { ...current, state: State.ERRO_REDE, returnTo: null };
    if (type === 'dismiss-error') {
        if (!ERRORS.has(current.state)) return current;
        return { ...current, state: State.E0, returnTo: null };
    }
    if (type === 'retry') {
        if (current.state === State.ERRO_CAMERA) {
            return { ...current, state: State.E1, returnTo: State.E0 };
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
let background = [];

function instructionFor(current) {
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
    const shell = document.getElementById('visitor-shell');
    if (shell) shell.dataset.state = session.state;
    routeBar.update(session);
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
    renderFlow();
    if (instructions) {
        const text = instructionFor(session);
        if (instructions.textContent !== text) instructions.textContent = text;
    }
}

function renderFlow() {
    if (!flow) return;
    flow.replaceChildren();
    const stub = session.state === State.E3 || session.state === State.E4 || session.state === State.E5;
    const error = ERRORS.has(session.state);
    flow.hidden = !stub && !error;
    if (!stub && !error) return;

    const title = document.createElement('p');
    title.className = 'flow-title';
    if (session.state === State.E3) {
        // TODO: E3 Prévia — desenhar a rota e confirmar antes de navegar.
        title.textContent = 'Prévia da rota';
        flow.append(title, flowButton('Confirmar prévia', 'Confirmar', 'confirm-preview'), flowButton('Voltar da prévia', 'Voltar', 'cancel-preview'));
        return;
    }
    if (session.state === State.E4) {
        // TODO: E4 Navegando — acompanhar o passo a passo no mapa.
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
    title.textContent = ERROR_TEXT[session.state] || 'Algo deu errado.';
    flow.append(title, flowButton('Voltar ao mapa', 'Voltar', 'dismiss-error'), flowButton('Tentar de novo', 'Tentar de novo', 'retry'));
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

function commit(next, source) {
    const effect = historyEffect(session, next);
    session = next;
    saveSession(toStored(session));
    if (source !== 'pop') {
        if (effect === 'push') {
            history.pushState({ povOverlay: session.state }, '', pageUrl(session));
        } else if (effect === 'back') {
            if (history.state && history.state.povOverlay) {
                render();
                history.back();
                return;
            }
        } else if (!sameUrl(session)) {
            history.replaceState(history.state, '', pageUrl(session));
        }
    }
    render();
}

export function dispatch(event) {
    commit(transition(session, event), 'ui');
}

function requestBack() {
    if ((session.state === State.E1 || session.state === State.E2) && history.state && history.state.povOverlay) {
        history.back();
        return;
    }
    dispatch({ type: 'back' });
}

function onPopState() {
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
    if (searchField) searchField.focus();
    dispatch({ type: 'open-search' });
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
        onClose: requestBack
    });
    camera = mountCameraOverlay(document.getElementById('camera-root'), {
        onClose: requestBack
    });

    session = {
        ...hydrateSession(location.hash),
        returnTo: null
    };
    saveSession(toStored(session));
    if (OVERLAYS.has(session.state)) {
        session.returnTo = State.E0;
        history.replaceState({}, '', pageUrl(session));
        history.pushState({ povOverlay: session.state }, '', pageUrl(session));
    } else if (!sameUrl(session)) {
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
    render();

    const mapHost = document.getElementById('visitor-map');
    if (mapHost) {
        mountMapView(mapHost).catch(() => {});
    }
}

if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', () => {
        if (document.body && document.body.dataset.app === 'visitor') mountVisitorApp();
    });
}
