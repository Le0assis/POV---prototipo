import { insertTopNav } from '../components/nav.js';
import { getMapConfig, saveMapConfig } from '../core/api.js';
import { $ } from '../core/dom.js';
import { whenAdminGranted } from '../core/role-toggle.js';
import { toast } from '../core/toast.js';
import { normalizeMapConfig } from '../route/model.js';
import {
    MAP_CONFIG_HELP,
    degreesFromRadians,
    formatMapConfigSaveError,
    validateMapConfigInput
} from './map-config-form.js';

document.addEventListener('DOMContentLoaded', init);

function init() {
    insertTopNav('admin');
    bindFieldHelp();
    whenAdminGranted(start);
}

function bindFieldHelp() {
    Object.entries(MAP_CONFIG_HELP).forEach(([key, text]) => {
        const tip = document.getElementById(`${key}-help`);
        const input = document.getElementById(key === 'rotation_deg' ? 'rotation-deg' : key === 'px_per_m' ? 'px-per-m' : 'plan-image');
        const button = document.querySelector(`[aria-controls="${key}-help"]`);
        if (tip) tip.textContent = text;
        if (input) input.setAttribute('aria-describedby', `${key}-help`);
        if (button) button.setAttribute('title', text);
    });
    document.querySelectorAll('.field-help').forEach((button) => {
        const tipId = button.getAttribute('aria-controls');
        const tip = tipId ? document.getElementById(tipId) : null;
        if (!tip) return;
        button.addEventListener('click', () => {
            const open = !tip.classList.contains('is-open');
            closeFieldHelp();
            tip.classList.toggle('is-open', open);
            button.setAttribute('aria-expanded', open ? 'true' : 'false');
        });
    });
    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape') return;
        closeFieldHelp();
    });
}

function closeFieldHelp() {
    document.querySelectorAll('.field-tip.is-open').forEach((tip) => tip.classList.remove('is-open'));
    document.querySelectorAll('.field-help[aria-expanded="true"]').forEach((button) => {
        button.setAttribute('aria-expanded', 'false');
    });
}

async function start() {
    $('#map-config-app').classList.remove('hidden');
    $('#form-map-config').addEventListener('submit', onSubmit);
    $('#rotation-deg').addEventListener('input', paintRotation);
    paintRotation();
    try {
        const config = normalizeMapConfig(await getMapConfig());
        if (!config) return;
        if (config.plan_image) $('#plan-image').value = config.plan_image;
        if (config.px_per_m != null) $('#px-per-m').value = String(config.px_per_m);
        if (config.rotation_rad != null) $('#rotation-deg').value = degreesFromRadians(config.rotation_rad);
        paintRotation();
    } catch (err) {
        toast(err.message || 'Planta ainda não configurada.', 'warn');
    }
}

function paintRotation() {
    const result = validateMapConfigInput({
        planImage: '',
        rawPx: '1',
        degrees: $('#rotation-deg').value
    });
    const rad = result.value ? result.value.rotation_rad : 0;
    $('#rotation-rad').textContent = rad.toFixed(4);
}

function showError(message) {
    const el = $('#map-config-error');
    el.textContent = message || '';
}

async function onSubmit(event) {
    event.preventDefault();
    const result = validateMapConfigInput({
        planImage: $('#plan-image').value,
        rawPx: $('#px-per-m').value,
        degrees: $('#rotation-deg').value
    });
    if (result.error) {
        showError(result.error);
        toast(result.error, 'warn');
        return;
    }
    showError('');
    try {
        await saveMapConfig(result.value);
        toast('Planta salva.', 'ok');
    } catch (err) {
        const message = formatMapConfigSaveError(err);
        showError(message);
        toast(message, 'erro');
    }
}
