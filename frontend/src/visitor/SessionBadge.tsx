import { visitorSession } from './session';

/** Estado do visitante. O mapa não entra nesta árvore. */
export function SessionBadge() {
    const current = visitorSession.value;
    const state = current && current.state ? current.state : 'E0';
    return <span class="sr-only" data-visitor-state={state}>{state}</span>;
}
