/**
 * Localização fixa no servidor. Só existe para teste.
 * O build de produção não importa este arquivo. A flag fica desligada.
 */

export const TEST_ROUTES_ENABLED = false;

export function localizeBody(stepLengthM, yawRad) {
    return { step_length_m: stepLengthM, yaw_rad: yawRad };
}

export function serverLocationPaths() {
    return ['/api/localize', '/api/current_location', '/api/reset'];
}
