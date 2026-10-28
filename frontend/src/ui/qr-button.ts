/**
 * Botão flutuante do QR. O ícone é o `qr-code` do Lucide (ISC).
 * Abre a câmera para ler o QR do ponto.
 */

const QR_ICON = `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
    <rect width="5" height="5" x="3" y="3" rx="1"></rect>
    <rect width="5" height="5" x="16" y="3" rx="1"></rect>
    <rect width="5" height="5" x="3" y="16" rx="1"></rect>
    <path d="M21 16h-3a2 2 0 0 0-2 2v3"></path>
    <path d="M21 21v.01"></path>
    <path d="M12 7v3a2 2 0 0 1-2 2H7"></path>
    <path d="M3 12h.01"></path>
    <path d="M12 3h.01"></path>
    <path d="M12 16v.01"></path>
    <path d="M16 12h1"></path>
    <path d="M21 12v.01"></path>
    <path d="M12 21v-1"></path>
</svg>`;

export function createQrButton({ onClick } = {} as any) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'qr-button';
    button.setAttribute('aria-label', 'Ler QR');
    button.innerHTML = QR_ICON;
    button.addEventListener('click', () => {
        if (typeof onClick === 'function') onClick();
    });
    return button;
}
