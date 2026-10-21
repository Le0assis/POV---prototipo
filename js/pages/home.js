import { insertTopNav } from '../components/nav.js';
import { ping } from '../core/api.js';
import { $ } from '../core/dom.js';

document.addEventListener('DOMContentLoaded', async () => {
    insertTopNav('home');
    const el = $('#home-api');
    const online = await ping();
    el.textContent = online ? 'online' : 'offline';
});
