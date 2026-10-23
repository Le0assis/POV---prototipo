/**
 * Formato do QR de checkpoint (v1) e a leitura compatível com o hash antigo.
 * Puro: não lê câmera, rede nem DOM.
 *
 * URL: `https://pov-unimar.com/#/scan?cp=<slug>&b=<building_id>&v=1`
 * Também vale qualquer host ou caminho, desde que exista `cp` (`b` opcional, `v` assume 1).
 * O hash `#origem=<slug>` continua valendo. Um slug solto é a digitação manual.
 */

export const QR_VERSION = 1;
export const QR_PAGE = 'https://pov-unimar.com/#/scan';

export const QrErrorCode = Object.freeze({
    invalid: 'invalid',
    unsupportedVersion: 'unsupported-version'
});

export class QrFormatError extends Error {
    code: any;

    constructor(code) {
        const known = code === QrErrorCode.unsupportedVersion
            ? QrErrorCode.unsupportedVersion
            : QrErrorCode.invalid;
        super(known);
        this.name = 'QrFormatError';
        this.code = known;
    }
}

function fail(code) {
    const error = new QrFormatError(code);
    return { error: error.code };
}

function slugText(value) {
    if (value == null) return '';
    return String(value).trim();
}

/**
 * Monta a URL v1. O gerador do admin (T8) usa isto.
 * Espaço vira `%20`. Sem slug, lança `QrFormatError`.
 */
export function buildQr({ cp, b } = {} as any) {
    const slug = slugText(cp);
    if (!slug) throw new QrFormatError(QrErrorCode.invalid);
    const pairs = [['cp', slug]];
    if (b != null && String(b).trim() !== '') pairs.push(['b', String(b).trim()]);
    pairs.push(['v', String(QR_VERSION)]);
    const query = pairs
        .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
        .join('&');
    return `${QR_PAGE}?${query}`;
}

function finish(cp, b, v) {
    const slug = slugText(cp);
    if (!slug) return fail(QrErrorCode.invalid);
    if (v != null && String(v).trim() !== '') {
        const version = String(v).trim();
        if (!/^[0-9]+$/.test(version) || Number(version) !== QR_VERSION) {
            return fail(QrErrorCode.unsupportedVersion);
        }
    }
    let building = null;
    if (b != null && String(b).trim() !== '') {
        const text = String(b).trim();
        if (!/^[0-9]+$/.test(text)) return fail(QrErrorCode.invalid);
        building = Number(text);
    }
    return { cp: slug, b: building, v: QR_VERSION };
}

function fromParams(params) {
    if (!params) return fail(QrErrorCode.invalid);
    const hasCp = params.has('cp');
    const hasOrigem = params.has('origem');
    if (!hasCp && !hasOrigem) return fail(QrErrorCode.invalid);
    return finish(
        hasCp ? params.get('cp') : params.get('origem'),
        params.has('b') ? params.get('b') : null,
        params.has('v') ? params.get('v') : null
    );
}

function paramsFromHashBody(hashBody) {
    const body = String(hashBody || '').replace(/^#/, '');
    const mark = body.indexOf('?');
    const query = mark >= 0 ? body.slice(mark + 1) : body;
    return new URLSearchParams(query);
}

function hashCarriesPoint(hashBody) {
    return /(?:^|[?&#])(cp|origem)=/.test(`#${hashBody}`);
}

function parseHashBody(hashBody) {
    const body = String(hashBody || '').replace(/^#/, '').trim();
    if (!body || !hashCarriesPoint(body)) return fail(QrErrorCode.invalid);
    return fromParams(paramsFromHashBody(body));
}

function parseAbsolute(raw) {
    let url;
    try {
        url = new URL(raw);
    } catch (_) {
        return fail(QrErrorCode.invalid);
    }
    const hashBody = url.hash.replace(/^#/, '');
    if (hashBody && hashCarriesPoint(hashBody)) return parseHashBody(hashBody);
    if (url.search) {
        const search = new URLSearchParams(url.search);
        if (search.has('cp') || search.has('origem')) return fromParams(search);
    }
    return fail(QrErrorCode.invalid);
}

function isBareSlug(raw) {
    if (!raw || raw.length > 200) return false;
    if (/[\u0000-\u001f]/.test(raw)) return false;
    if (/[?#=&/\\]/.test(raw)) return false;
    return /^[\p{L}\p{N}]/u.test(raw);
}

/**
 * @returns {{ cp: string, b: number|null, v: number } | { error: 'invalid' | 'unsupported-version' }}
 */
export function parseQr(text) {
    const raw = text == null ? '' : String(text).trim();
    if (!raw) return fail(QrErrorCode.invalid);
    if (/^[a-z][a-z0-9+.-]*:/i.test(raw)) return parseAbsolute(raw);
    if (raw.startsWith('#')) return parseHashBody(raw);
    if (raw.includes('cp=') || raw.includes('origem=')) {
        const asHash = raw.startsWith('/') || raw.startsWith('?') ? raw : raw;
        return parseHashBody(asHash.includes('?') || asHash.includes('=') ? asHash : `#${asHash}`);
    }
    if (!isBareSlug(raw)) return fail(QrErrorCode.invalid);
    return { cp: raw, b: null, v: QR_VERSION };
}

/**
 * Hash aberto pela câmera nativa do celular: `#/scan?cp=&b=&v=`.
 * `null` quando o hash não é um scan (o `#origem=` fica com a sessão).
 */
export function parseScanLocation(value) {
    const text = value == null ? '' : String(value).trim();
    if (!text.includes('/scan')) return null;
    if (text.startsWith('#') || /^[a-z][a-z0-9+.-]*:/i.test(text)) return parseQr(text);
    return parseQr(text.startsWith('/') ? `#${text}` : `#/${text}`);
}
