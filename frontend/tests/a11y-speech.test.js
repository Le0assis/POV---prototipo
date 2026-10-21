import assert from 'node:assert/strict';
import test from 'node:test';

import { effectiveSpeech, speakInstruction, speechSupported } from '../js/a11y/speech.js';

test('sem a Web Speech API a leitura fica desligada', () => {
    assert.equal(speechSupported(), false);
    assert.equal(speechSupported({ synth: null, Utterance: null }), false);
    assert.equal(speakInstruction('Siga em frente por 10 m', { enabled: true }), false);
    assert.equal(effectiveSpeech({ speech: true }, false), false);
    assert.equal(effectiveSpeech({ speech: true }, speechSupported()), false);

    const spoken = [];
    const synth = {
        cancel() {},
        speak(utter) { spoken.push(utter); }
    };
    assert.equal(speakInstruction('Siga em frente', {
        enabled: true,
        synth,
        Utterance: null
    }), false);
    assert.equal(spoken.length, 0);
});

test('com a API, fala em pt-BR só quando a preferência está ligada', () => {
    const spoken = [];
    const synth = {
        cancel() {},
        speak(utter) { spoken.push(utter); }
    };
    class Utterance {
        constructor(text) {
            this.text = text;
            this.lang = '';
        }
    }
    assert.equal(speechSupported({ synth, Utterance }), true);
    assert.equal(effectiveSpeech({ speech: false }, true), false);
    assert.equal(speakInstruction('Siga em frente', {
        enabled: false,
        synth,
        Utterance
    }), false);
    assert.equal(spoken.length, 0);

    assert.equal(speakInstruction('Siga em frente por 12 m', {
        enabled: true,
        synth,
        Utterance
    }), true);
    assert.equal(spoken.length, 1);
    assert.equal(spoken[0].text, 'Siga em frente por 12 m');
    assert.equal(spoken[0].lang, 'pt-BR');

    assert.equal(speakInstruction('   ', { enabled: true, synth, Utterance }), false);
});
