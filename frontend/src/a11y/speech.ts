/**
 * Leitura das instruções do banner (T7) com a Web Speech API.
 * Sem `speechSynthesis` ou sem `SpeechSynthesisUtterance`, a leitura fica desligada.
 */

const PT_BR = 'pt-BR';

export function speechSupported({ synth, Utterance } = {} as any) {
    const engine = synth === undefined ? globalSpeech() : synth;
    const Ctor = Utterance === undefined ? globalUtterance() : Utterance;
    return Boolean(
        engine
        && typeof engine.speak === 'function'
        && typeof engine.cancel === 'function'
        && typeof Ctor === 'function'
    );
}

/** A preferência gravada não liga a voz quando o aparelho não tem a API. */
export function effectiveSpeech(prefs, support) {
    const enabled = Boolean(prefs && prefs.speech);
    const ok = support === undefined ? speechSupported() : Boolean(support);
    return enabled && ok;
}

export function cancelSpeech(synth = undefined) {
    const engine = synth === undefined ? globalSpeech() : synth;
    if (engine && typeof engine.cancel === 'function') engine.cancel();
}

/**
 * Fala `text` em pt-BR. Devolve false sem falar quando a voz está desligada
 * ou quando a API não existe.
 */
export function speakInstruction(text, { enabled = false, synth, Utterance, lang = PT_BR } = {} as any) {
    const engine = synth === undefined ? globalSpeech() : synth;
    const Ctor = Utterance === undefined ? globalUtterance() : Utterance;
    if (!enabled || !speechSupported({ synth: engine, Utterance: Ctor })) return false;
    const phrase = text == null ? '' : String(text).trim();
    if (!phrase) {
        cancelSpeech(engine);
        return false;
    }
    cancelSpeech(engine);
    const utter = new Ctor(phrase);
    utter.lang = lang;
    engine.speak(utter);
    return true;
}

function globalSpeech() {
    try {
        return typeof globalThis.speechSynthesis === 'undefined' ? null : globalThis.speechSynthesis;
    } catch (_) {
        return null;
    }
}

function globalUtterance() {
    try {
        return typeof globalThis.SpeechSynthesisUtterance === 'function'
            ? globalThis.SpeechSynthesisUtterance
            : null;
    } catch (_) {
        return null;
    }
}
