/**
 * Entrada separada do mapa e da navegação: o seletor de papel não entra
 * no grafo de imports dessas páginas.
 */

import { isAdminPath, mountRoleChrome, requireAdminAccess } from './core/role-toggle.js';

document.addEventListener('DOMContentLoaded', () => {
    mountRoleChrome();
    if (isAdminPath(window.location.pathname)) requireAdminAccess();
});
