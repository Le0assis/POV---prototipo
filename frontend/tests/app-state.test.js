import assert from 'node:assert/strict';
import test from 'node:test';

import { State, canStartRoute, historyEffect, transition } from '../js/app.js';

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

test('origem e destino entram por slug ou por objeto', () => {
    const withSlug = transition(session(), { type: 'set-origin', origin: 'recepcao' });
    assert.deepEqual(withSlug.origin, { slug: 'recepcao', label: 'recepcao' });
    const named = transition(withSlug, { type: 'set-destination', destination: destination });
    assert.equal(named.destination.label, 'Sala');
    assert.equal(transition(named, { type: 'clear-origin' }).origin, null);
    assert.equal(historyEffect(State.E0, State.E0), 'none');
});
