import assert from 'node:assert/strict';
import test from 'node:test';

import {
    State,
    canStartRoute,
    emitRecalibrate,
    historyEffect,
    shouldRecalibrate,
    showsRoute,
    transition
} from '../js/app.js';

function session(partial = {}) {
    return {
        origin: null,
        destination: null,
        state: State.E0,
        returnTo: null,
        ...partial
    };
}

const origin = { slug: 'recepcao', label: 'Recepção' };
const destination = { slug: 'sala', label: 'Sala' };

test('E0 abre câmera e busca e o voltar desfaz', () => {
    const camera = transition(session(), { type: 'open-camera' });
    assert.equal(camera.state, State.E1);
    assert.equal(camera.returnTo, State.E0);
    assert.equal(transition(camera, { type: 'back' }).state, State.E0);

    const search = transition(session(), { type: 'open-search' });
    assert.equal(search.state, State.E2);
    assert.equal(search.returnTo, State.E0);
    assert.equal(transition(search, { type: 'close-overlay' }).state, State.E0);
});

test('trocar de câmera para busca não empilha e volta ao estado anterior', () => {
    const preview = session({ origin, destination, state: State.E3 });
    const camera = transition(preview, { type: 'open-camera' });
    assert.equal(camera.state, State.E1);
    assert.equal(camera.returnTo, State.E3);
    const search = transition(camera, { type: 'open-search' });
    assert.equal(search.state, State.E2);
    assert.equal(search.returnTo, State.E3);
    assert.equal(search.origin.slug, 'recepcao');
    assert.equal(search.destination.slug, 'sala');
    assert.equal(transition(search, { type: 'back' }).state, State.E3);
    assert.equal(historyEffect(preview, camera), 'push');
    assert.equal(historyEffect(camera, search), 'none');
    assert.equal(historyEffect(search, transition(search, { type: 'back' })), 'back');
});

test('iniciar rota exige os dois pontos e segue até a chegada', () => {
    const bare = session();
    assert.equal(canStartRoute(bare), false);
    assert.equal(transition(bare, { type: 'start-route' }).state, State.E0);

    const ready = session({ origin, destination });
    assert.equal(canStartRoute(ready), true);
    const preview = transition(ready, { type: 'start-route' });
    assert.equal(preview.state, State.E3);
    const walking = transition(preview, { type: 'confirm-preview' });
    assert.equal(walking.state, State.E4);
    const arrived = transition(walking, { type: 'arrive' });
    assert.equal(arrived.state, State.E5);
    const done = transition(arrived, { type: 'finish' });
    assert.equal(done.state, State.E0);
    assert.equal(done.origin.slug, 'recepcao');
    assert.equal(done.destination.slug, 'sala');
});

test('E3, E4 e E5 recuam pelo voltar e pelos cancelamentos', () => {
    const preview = session({ origin, destination, state: State.E3 });
    assert.equal(transition(preview, { type: 'cancel-preview' }).state, State.E0);
    assert.equal(transition(preview, { type: 'back' }).state, State.E0);

    const walking = session({ origin, destination, state: State.E4 });
    assert.equal(transition(walking, { type: 'back' }).state, State.E3);
    assert.equal(transition(walking, { type: 'stop-navigation' }).state, State.E0);
    assert.equal(transition(session({ state: State.E5 }), { type: 'back' }).state, State.E0);
});

test('erros de câmera, rota, mapa e rede entram e saem', () => {
    const cameraError = transition(session({ state: State.E1, returnTo: State.E0 }), { type: 'camera-error' });
    assert.equal(cameraError.state, State.ERRO_CAMERA);
    assert.equal(transition(cameraError, { type: 'dismiss-error' }).state, State.E0);
    assert.equal(transition(cameraError, { type: 'retry' }).state, State.E1);

    const routeError = transition(session({ origin, destination, state: State.E3 }), { type: 'route-error' });
    assert.equal(routeError.state, State.ERRO_ROTA);
    assert.equal(transition(routeError, { type: 'retry' }).state, State.E3);
    assert.equal(transition(session({ state: State.ERRO_ROTA }), { type: 'retry' }).state, State.E0);

    assert.equal(transition(session(), { type: 'map-error' }).state, State.ERRO_MAPA);
    assert.equal(transition(session(), { type: 'network-error' }).state, State.ERRO_REDE);
    assert.equal(transition(session({ state: State.ERRO_MAPA }), { type: 'back' }).state, State.E0);
    assert.equal(transition(session({ state: State.ERRO_REDE }), { type: 'retry' }).state, State.E0);
});

test('eventos fora de hora não mudam o estado e a sessão original fica intacta', () => {
    const current = session({ origin, destination, state: State.E0 });
    assert.equal(transition(current, { type: 'confirm-preview' }).state, State.E0);
    assert.equal(transition(current, { type: 'arrive' }).state, State.E0);
    assert.equal(transition(current, { type: 'finish' }).state, State.E0);
    assert.equal(transition(session({ state: State.E1 }), { type: 'start-route' }).state, State.E1);
    assert.equal(transition(session({ origin, destination, state: State.E4 }), { type: 'start-route' }).state, State.E4);
    assert.equal(transition(session({ state: State.E1 }), { type: 'open-camera' }).state, State.E1);
    assert.equal(transition(current, { type: 'dismiss-error' }).state, State.E0);

    const next = transition(current, { type: 'clear-destination' });
    assert.equal(current.destination.slug, 'sala');
    assert.equal(current.state, State.E0);
    assert.equal(next.destination, null);
    assert.notEqual(next, current);
});

test('escolher um destino na busca vai para a prévia e fecha a folha', () => {
    const search = transition(session(), { type: 'open-search' });
    assert.equal(search.state, State.E2);

    const preview = transition(search, {
        type: 'select-destination',
        destination: { slug: 'sala', label: 'Sala' }
    });
    assert.equal(preview.state, State.E3);
    assert.deepEqual(preview.destination, { slug: 'sala', label: 'Sala' });
    assert.equal(preview.origin, null);
    assert.equal(preview.returnTo, null);
    assert.equal(canStartRoute(preview), false);
    assert.equal(historyEffect(search, preview), 'back');

    const stayed = transition(search, { type: 'select-destination', destination: '  ' });
    assert.equal(stayed.state, State.E2);
    assert.equal(stayed.destination, null);

    const withOrigin = transition(session({ origin, state: State.E2, returnTo: State.E0 }), {
        type: 'select-destination',
        destination: 'copa'
    });
    assert.equal(withOrigin.state, State.E3);
    assert.equal(withOrigin.origin.slug, 'recepcao');
    assert.equal(withOrigin.destination.slug, 'copa');
    assert.equal(canStartRoute(withOrigin), true);

    const walking = session({ origin, destination, state: State.E4 });
    assert.equal(transition(walking, { type: 'select-destination', destination: 'copa' }).state, State.E4);
});

test('ler o QR na câmera fecha em E0 sem destino e em E3 com destino', () => {
    const camera = transition(session(), { type: 'open-camera' });
    const located = transition(camera, {
        type: 'qr-resolved',
        origin: { slug: 'recepcao', label: 'Recepção' }
    });
    assert.equal(located.state, State.E0);
    assert.deepEqual(located.origin, { slug: 'recepcao', label: 'Recepção' });
    assert.equal(located.returnTo, null);
    assert.equal(located.announceOrigin, true);
    assert.equal(historyEffect(camera, located), 'back');
    assert.equal(shouldRecalibrate(camera, { type: 'qr-resolved', origin: located.origin }), false);

    const preview = transition(session({ destination, state: State.E1, returnTo: State.E0 }), {
        type: 'qr-resolved',
        origin
    });
    assert.equal(preview.state, State.E3);
    assert.equal(preview.destination.slug, 'sala');
    assert.equal(preview.origin.slug, 'recepcao');
    assert.equal(canStartRoute(preview), true);
    assert.equal(historyEffect(session({ state: State.E1 }), preview), 'back');
});

test('QR durante a navegação recalibra e não cancela a rota', () => {
    const walking = session({ origin, destination, state: State.E4 });
    const camera = transition(walking, { type: 'open-camera' });
    assert.equal(camera.state, State.E1);
    assert.equal(camera.returnTo, State.E4);
    const event = { type: 'qr-resolved', origin: { slug: 'hall', label: 'Hall' } };
    assert.equal(shouldRecalibrate(camera, event), true);
    assert.equal(shouldRecalibrate(walking, event), true);
    const next = transition(camera, event);
    assert.equal(next.state, State.E4);
    assert.deepEqual(next.origin, { slug: 'hall', label: 'Hall' });
    assert.equal(next.destination.slug, 'sala');
    assert.equal(historyEffect(camera, next), 'back');

    const target = new EventTarget();
    let detail = null;
    target.addEventListener('recalibrate', (heard) => {
        detail = heard.detail;
    });
    const emitted = emitRecalibrate(next.origin, target);
    assert.equal(emitted.type, 'recalibrate');
    assert.equal(detail.origin.slug, 'hall');
});

test('câmera negada durante a navegação volta para E4', () => {
    const failed = transition(session({ origin, destination, state: State.E1, returnTo: State.E4 }), {
        type: 'camera-error',
        message: 'A permissão da câmera foi negada. Libere o acesso nas configurações do navegador ou digite o código do ponto.'
    });
    assert.equal(failed.state, State.ERRO_CAMERA);
    assert.equal(failed.returnTo, State.E4);
    assert.match(failed.cameraMessage, /negada/);
    assert.equal(transition(failed, { type: 'retry' }).state, State.E1);
    assert.equal(transition(failed, { type: 'retry' }).returnTo, State.E4);
    assert.equal(transition(failed, { type: 'dismiss-error' }).state, State.E4);
    assert.equal(transition(failed, { type: 'qr-resolved', origin: { slug: 'hall', label: 'Hall' } }).state, State.E4);
});

test('E3 troca destino e origem, e Iniciar rota vai para E4', () => {
    const preview = session({ origin, destination, state: State.E3 });
    assert.equal(showsRoute(State.E3), true);
    assert.equal(showsRoute(State.E4), true);
    assert.equal(showsRoute(State.E0), false);
    assert.equal(showsRoute(State.E5), false);
    assert.equal(showsRoute(State.ERRO_ROTA), false);

    const swapped = transition(preview, {
        type: 'select-destination',
        destination: { slug: 'copa', label: 'Copa' }
    });
    assert.equal(swapped.state, State.E3);
    assert.equal(swapped.destination.slug, 'copa');
    assert.equal(swapped.origin.slug, 'recepcao');

    const moved = transition(preview, {
        type: 'qr-resolved',
        origin: { slug: 'hall', label: 'Hall' }
    });
    assert.equal(moved.state, State.E3);
    assert.equal(moved.origin.slug, 'hall');
    assert.equal(moved.destination.slug, 'sala');
    assert.equal(shouldRecalibrate(preview, { type: 'qr-resolved', origin: moved.origin }), false);

    assert.equal(transition(preview, { type: 'start-route' }).state, State.E4);
    assert.equal(transition(preview, { type: 'confirm-preview' }).state, State.E4);
    const noOrigin = session({ destination, state: State.E3 });
    assert.equal(canStartRoute(noOrigin), false);
    assert.equal(transition(noOrigin, { type: 'confirm-preview' }).state, State.E3);
    assert.equal(transition(noOrigin, { type: 'start-route' }).state, State.E3);
});

test('ERRO_ROTA abre a busca para trocar o destino e volta à prévia', () => {
    const failed = transition(session({ origin, destination, state: State.E3 }), { type: 'route-error' });
    assert.equal(failed.state, State.ERRO_ROTA);
    assert.equal(showsRoute(failed.state), false);
    const search = transition(failed, { type: 'open-search' });
    assert.equal(search.state, State.E2);
    assert.equal(search.origin.slug, 'recepcao');
    const next = transition(search, {
        type: 'select-destination',
        destination: { slug: 'copa', label: 'Copa' }
    });
    assert.equal(next.state, State.E3);
    assert.equal(next.destination.slug, 'copa');
    assert.equal(next.origin.slug, 'recepcao');
    assert.equal(showsRoute(next.state), true);
});

test('origem e destino entram por slug ou por objeto', () => {
    const withSlug = transition(session(), { type: 'set-origin', origin: 'recepcao' });
    assert.deepEqual(withSlug.origin, { slug: 'recepcao', label: 'recepcao' });
    const named = transition(withSlug, { type: 'set-destination', destination: destination });
    assert.equal(named.destination.label, 'Sala');
    assert.equal(transition(named, { type: 'clear-origin' }).origin, null);
    assert.equal(historyEffect(State.E0, State.E0), 'none');
});
