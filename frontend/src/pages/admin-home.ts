import { insertTopNav } from '../components/nav.js';
import { whenAdminGranted } from '../core/role-toggle.js';

document.addEventListener('DOMContentLoaded', () => {
    insertTopNav('admin');
    whenAdminGranted(() => {
        const menu = document.getElementById('admin-menu');
        if (menu) menu.classList.remove('hidden');
    });
});
