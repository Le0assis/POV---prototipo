import { mountMapView } from './map-view.js';

/** Leaflet fica fora do Preact: o componente só entrega o elemento. */
export class MapController {
    private readonly host: HTMLElement;

    constructor(host: HTMLElement) {
        this.host = host;
    }

    mount() {
        return mountMapView(this.host);
    }
}
