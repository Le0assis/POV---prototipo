/**
 * Botão e painel de acessibilidade do visitante.
 * Alto contraste e fonte grande gravam em localStorage e entram em `html`
 * na hora. A leitura em voz alta só existe quando a Web Speech API existe.
 */

import { applyA11yClasses, readA11yPrefs, saveA11yPrefs } from '../a11y/prefs.js';
import { cancelSpeech, effectiveSpeech, speakInstruction, speechSupported } from '../a11y/speech.js';
import { focusableElements, trapTabKey } from './focus-trap.js';
import { lucideIcon } from './icons.js';

export function mountA11yControl(slot) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'a11y-button';
    button.id = 'a11y-button';
    button.setAttribute('aria-label', 'Acessibilidade');
    button.setAttribute('aria-haspopup', 'dialog');
    button.setAttribute('aria-expanded', 'false');
    button.setAttribute('aria-controls', 'a11y-panel');
    const icon = lucideIcon('accessibility');
    if (icon) {
        icon.setAttribute('width', '48');
        icon.setAttribute('height', '48');
        button.append(icon);
    }

    const panel = document.createElement('div');
    panel.id = 'a11y-panel';
    panel.className = 'a11y-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-labelledby', 'a11y-title');
    panel.hidden = true;

    const title = document.createElement('h2');
    title.id = 'a11y-title';
    title.className = 'a11y-title';
    title.textContent = 'Acessibilidade';

    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'btn btn-ghost a11y-close';
    close.textContent = 'Fechar';
    close.setAttribute('aria-label', 'Fechar acessibilidade');

    const head = document.createElement('div');
    head.className = 'a11y-head';
    head.append(title);

    const hcInput = switchInput('a11y-hc', 'Alto contraste');
    const fontInput = switchInput('a11y-font', 'Fonte grande');
    const speechInput = switchInput('a11y-speech', 'Ler instruções em voz alta');
    const speechHint = document.createElement('p');
    speechHint.id = 'a11y-speech-hint';
    speechHint.className = 'hint';
    speechHint.textContent = 'Este aparelho não lê em voz alta.';

    const voice = speechSupported();
    speechInput.disabled = !voice;
    if (!voice) {
        speechInput.setAttribute('aria-describedby', 'a11y-speech-hint');
        speechHint.hidden = false;
    } else {
        speechHint.hidden = true;
    }

    panel.append(head, hcInput.label, fontInput.label, speechInput.label, speechHint, close);
    slot.append(button);
    document.body.append(panel);

    let open = false;
    let prefs = readA11yPrefs();
    paint(prefs);

    function paint(next) {
        prefs = next;
        applyA11yClasses(document.documentElement, prefs);
        hcInput.input.checked = prefs.hc;
        fontInput.input.checked = prefs.fontLg;
        speechInput.input.checked = voice && prefs.speech;
    }

    function persist(partial) {
        const stored = {
            hc: partial.hc,
            fontLg: partial.fontLg,
            speech: voice ? partial.speech : prefs.speech
        };
        paint(saveA11yPrefs(stored));
        if (!effectiveSpeech(prefs, voice)) cancelSpeech();
    }

    function readForm() {
        return {
            hc: hcInput.input.checked,
            fontLg: fontInput.input.checked,
            speech: speechInput.input.checked
        };
    }

    function shell() {
        return document.getElementById('visitor-shell');
    }

    function place() {
        const rect = button.getBoundingClientRect();
        const width = Math.min(320, Math.max(220, window.innerWidth - 16));
        let left = rect.left + (rect.width / 2) - (width / 2);
        left = Math.max(8, Math.min(left, window.innerWidth - width - 8));
        const below = rect.bottom + 8;
        const estimated = Math.min(panel.scrollHeight || 280, Math.round(window.innerHeight * 0.7));
        const top = below + estimated > window.innerHeight - 8
            ? Math.max(8, rect.top - estimated - 8)
            : below;
        panel.style.width = `${width}px`;
        panel.style.left = `${left}px`;
        panel.style.top = `${top}px`;
    }

    function onKey(event) {
        if (!open) return;
        if (event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            closePanel();
            return;
        }
        trapTabKey(panel, event);
    }

    function onPointer(event) {
        if (!open) return;
        if (panel.contains(event.target) || button.contains(event.target)) return;
        closePanel();
    }

    function openPanel() {
        if (open) return;
        open = true;
        panel.hidden = false;
        button.setAttribute('aria-expanded', 'true');
        const host = shell();
        if (host) host.inert = true;
        place();
        document.addEventListener('keydown', onKey);
        document.addEventListener('pointerdown', onPointer);
        const nodes = focusableElements(panel);
        if (nodes[0]) nodes[0].focus();
        else close.focus();
    }

    function closePanel() {
        if (!open) return;
        open = false;
        panel.hidden = true;
        button.setAttribute('aria-expanded', 'false');
        const host = shell();
        if (host) host.inert = false;
        document.removeEventListener('keydown', onKey);
        document.removeEventListener('pointerdown', onPointer);
        if (typeof button.focus === 'function') button.focus();
    }

    button.addEventListener('click', () => {
        if (open) closePanel();
        else openPanel();
    });
    close.addEventListener('click', closePanel);
    hcInput.input.addEventListener('change', () => persist(readForm()));
    fontInput.input.addEventListener('change', () => persist(readForm()));
    speechInput.input.addEventListener('change', () => persist(readForm()));
    window.addEventListener('resize', () => {
        if (open) place();
    });

    function speak(text) {
        return speakInstruction(text, { enabled: effectiveSpeech(prefs, voice) });
    }

    return {
        button,
        panel,
        speak,
        open: openPanel,
        close: closePanel,
        isOpen: () => open
    };
}

function switchInput(id, text) {
    const label = document.createElement('label');
    label.className = 'a11y-toggle';
    label.setAttribute('for', id);
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.id = id;
    input.setAttribute('role', 'switch');
    const span = document.createElement('span');
    span.textContent = text;
    label.append(input, span);
    return { label, input };
}
