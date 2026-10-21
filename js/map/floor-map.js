/**
 * Mapa Leaflet em L.CRS.Simple: planta como imageOverlay, plano, sem inclinação.
 * Coordenadas de desenho são pixels da imagem (origem no canto superior esquerdo, y para baixo).
 */

export function createFloorMap(element) {
    if (typeof L === 'undefined') {
        throw new Error('Leaflet não carregou.');
    }
    const map = L.map(element, {
        crs: L.CRS.Simple,
        minZoom: -4,
        maxZoom: 4,
        zoomSnap: 0.25,
        attributionControl: true,
        bounceAtZoomLimits: false
    });

    const checkpoints = L.layerGroup().addTo(map);
    const connections = L.layerGroup().addTo(map);
    const locateLayer = L.layerGroup().addTo(map);

    let imageHeight = null;
    let imageWidth = null;
    let overlay = null;

    function pixelToLatLng(px, py) {
        const x = Number(px);
        const y = Number(py);
        if (imageHeight) return L.latLng(imageHeight - y, x);
        return L.latLng(-y, x);
    }

    function latLngToPixel(latlng) {
        const py = imageHeight ? imageHeight - latlng.lat : -latlng.lat;
        return { pos_x_px: latlng.lng, pos_y_px: py };
    }

    function clearPlan() {
        if (overlay) {
            map.removeLayer(overlay);
            overlay = null;
        }
        imageHeight = null;
        imageWidth = null;
    }

    async function setPlan(url) {
        clearPlan();
        if (!url) return null;
        const size = await loadImageSize(url);
        imageWidth = size.width;
        imageHeight = size.height;
        const bounds = L.latLngBounds([0, 0], [imageHeight, imageWidth]);
        overlay = L.imageOverlay(url, bounds).addTo(map);
        overlay.bringToBack();
        map.fitBounds(bounds);
        return { width: imageWidth, height: imageHeight };
    }

    function fitToContent(pixels) {
        const pts = (pixels || []).filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
        if (imageWidth && imageHeight) {
            map.fitBounds(L.latLngBounds([0, 0], [imageHeight, imageWidth]));
            return;
        }
        if (pts.length === 0) {
            map.setView(pixelToLatLng(0, 0), 0);
            return;
        }
        const bounds = L.latLngBounds(pts.map((p) => pixelToLatLng(p.x, p.y)));
        map.fitBounds(bounds.pad(0.4));
    }

    return {
        map,
        checkpoints,
        connections,
        locateLayer,
        pixelToLatLng,
        latLngToPixel,
        setPlan,
        clearPlan,
        fitToContent
    };
}

/**
 * Caminho relativo servido na raiz do frontend (GitHub Pages / pasta frontend).
 * Páginas em /admin/ não podem resolver assets/ a partir da própria URL.
 */
export function resolvePlanImage(planImage, pageHref) {
    if (!planImage) return '';
    const value = String(planImage).trim();
    if (!value) return '';
    if (/^https?:\/\//i.test(value)) return value;
    const href = pageHref || (typeof window === 'undefined' ? '' : window.location.href);
    if (!href) return value;
    return new URL(value, planImageBase(href)).href;
}

export function planImageBase(pageHref) {
    const url = new URL(pageHref);
    url.hash = '';
    url.search = '';
    const parts = url.pathname.split('/').filter(Boolean);
    if (parts.length && parts[parts.length - 1].includes('.')) parts.pop();
    if (parts.length && parts[parts.length - 1] === 'admin') parts.pop();
    url.pathname = `/${parts.join('/')}${parts.length ? '/' : ''}`;
    if (!url.pathname.endsWith('/')) url.pathname += '/';
    return url.href;
}

function loadImageSize(url) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve({
            width: img.naturalWidth,
            height: img.naturalHeight
        });
        img.onerror = () => reject(new Error('Não foi possível carregar a planta.'));
        img.src = url;
    });
}
