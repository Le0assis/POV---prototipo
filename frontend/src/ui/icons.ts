/**
 * Ícones Lucide usados na categoria do destino.
 * Nome desconhecido não desenha nada: a linha segue só com o texto.
 */

const NS = 'http://www.w3.org/2000/svg';

const ICONS = {
    accessibility: [
        ['circle', { cx: '16', cy: '4', r: '1' }],
        ['path', { d: 'm18 19 1-7-6 1' }],
        ['path', { d: 'm5 8 3-3 5.5 3-2.36 3.5' }],
        ['path', { d: 'M4.24 14.5a5 5 0 0 0 6.88 6' }],
        ['path', { d: 'M13.76 17.5a5 5 0 0 0-6.88-6' }]
    ],
    bath: [
        ['path', { d: 'M10 4 8 6' }],
        ['path', { d: 'M17 19v2' }],
        ['path', { d: 'M2 12h20' }],
        ['path', { d: 'M7 19v2' }],
        ['path', { d: 'M9 5 7.621 3.621A2.121 2.121 0 0 0 4 5v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5' }]
    ],
    coffee: [
        ['path', { d: 'M10 2v2' }],
        ['path', { d: 'M14 2v2' }],
        ['path', { d: 'M16 8a1 1 0 0 1 1 1v8a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V9a1 1 0 0 1 1-1h14a4 4 0 1 1 0 8h-1' }],
        ['path', { d: 'M6 2v2' }]
    ],
    'concierge-bell': [
        ['path', { d: 'M3 20a1 1 0 0 1-1-1v-1a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v1a1 1 0 0 1-1 1Z' }],
        ['path', { d: 'M20 16a8 8 0 1 0-16 0' }],
        ['path', { d: 'M12 4v4' }],
        ['path', { d: 'M10 4h4' }]
    ],
    'door-open': [
        ['path', { d: 'M10 21H2' }],
        ['path', { d: 'M10 3H7a2 2 0 00-2 2v16' }],
        ['path', { d: 'M14 12h.01' }],
        ['path', { d: 'M19 21V5a2 2 0 00-1.675-1.974l-6.163-1.013A1 1 0 0010 3v18a1 1 0 001.124.992z' }],
        ['path', { d: 'M22 21h-3' }]
    ],
    'map-pin': [
        ['path', { d: 'M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0' }],
        ['circle', { cx: '12', cy: '10', r: '3' }]
    ],
    utensils: [
        ['path', { d: 'M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2' }],
        ['path', { d: 'M7 2v20' }],
        ['path', { d: 'M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7' }]
    ]
};

export function lucideIcon(name) {
    const spec = name ? ICONS[String(name).trim().toLowerCase()] : null;
    if (!spec || typeof document === 'undefined') return null;
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('width', '24');
    svg.setAttribute('height', '24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    spec.forEach(([tag, attrs]) => {
        const node = document.createElementNS(NS, tag);
        Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
        svg.append(node);
    });
    return svg;
}
