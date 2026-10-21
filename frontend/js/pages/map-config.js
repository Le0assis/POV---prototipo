import { insertTopNav } from '../components/nav.js';
import { getMapConfig, saveMapConfig } from '../core/api.js';
import { $ } from '../core/dom.js';
import { whenAdminGranted } from '../core/role-toggle.js';
import { toast } from '../ui/toast.js';
import { normalizeMapConfig } from '../route/model.js';
import {
    degreesFromRadians,
    formatMapConfigSaveError,
    validateMapConfigInput
} from './map-config-form.js';

document.addEventListener('DOMContentLoaded', init);

function init() {
    insertTopNav('admin');
    whenAdminGranted(start);
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
