/**
 * Componente de navegação superior compartilhado
 * Usado em index.html, recorder.html e routes.html
 */

export function renderTopNav(activePage) {
    const nav = document.createElement('nav');
    nav.className = 'top-nav';
    nav.innerHTML = `
        <a href="/" class="nav-btn ${activePage === 'nav' ? 'active' : ''}">📍 Navegação</a>
        <a href="/recorder" class="nav-btn ${activePage === 'map' ? 'active' : ''}">🗺️ Mapeador</a>
        <a href="/routes" class="nav-btn ${activePage === 'routes' ? 'active' : ''}">📋 Rotas</a>
    `;
    return nav;
}

export function insertTopNav(activePage) {
    const nav = renderTopNav(activePage);
    // Insere no início do body
    document.body.insertBefore(nav, document.body.firstChild);
}