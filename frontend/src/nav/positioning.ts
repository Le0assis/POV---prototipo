/**
 * Posição por passos e heading, encaixada numa polilinha.
 * A conversão horário → anti-horário fica só em sensors/angles.js
 * (`relativeHeadingRad`). No E4 a polilinha é a rota atual, não o grafo inteiro.
 * O reinício é local: este módulo não fala com o servidor.
 */

import { pixelsToMeters } from '../map/units.js';
import { projectOntoSegment } from '../route/snap.js';
import { relativeHeadingRad, radToDeg, signedDelta } from '../sensors/angles.js';

export const ARRIVAL_M = 2;
export const TURN_THRESHOLD_DEG = 30;
export const NO_SENSORS_NOTICE = 'Sem sensores: siga a rota no mapa e leia os QR codes pelo caminho';

const BACK_WINDOW_M = 0.75;
const AHEAD_SLACK_M = 1.5;

export function sensorsPresent(env = globalThis) {
    return typeof env.DeviceMotionEvent === 'function'
        && typeof env.DeviceOrientationEvent === 'function';
}

/** `fallback` quando falta sensor ou a permissão foi negada. */
export function resolveSensorMode({
    present = false,
    motionGranted = false,
    orientationGranted = false,
    forcedOff = false
} = {} as any) {
    if (forcedOff || !present) return 'fallback';
    if (!motionGranted || !orientationGranted) return 'fallback';
    return 'live';
}

export function measurePolyline(points) {
    const clean = [];
    (Array.isArray(points) ? points : []).forEach((point) => {
        const x = Number(point && point.x);
        const y = Number(point && point.y);
        if (!Number.isFinite(x) || !Number.isFinite(y)) return;
        const last = clean[clean.length - 1];
        if (last && Math.hypot(last.x - x, last.y - y) < 1e-9) return;
        clean.push({ x, y });
    });
    const cumulative = [0];
    for (let i = 1; i < clean.length; i += 1) {
        const dx = clean[i].x - clean[i - 1].x;
        const dy = clean[i].y - clean[i - 1].y;
        cumulative.push(cumulative[i - 1] + Math.hypot(dx, dy));
    }
    return {
        points: clean,
        cumulative,
        length: cumulative[cumulative.length - 1] || 0
    };
}

export function tangentAt(metric, alongM) {
    const points = metric && metric.points;
    if (!points || points.length < 2) return 0;
    const along = Math.max(0, Math.min(metric.length, Number(alongM) || 0));
    let index = 0;
    for (let i = 0; i < points.length - 1; i += 1) {
        index = i;
        if (metric.cumulative[i + 1] >= along - 1e-9) break;
    }
    const a = points[index];
    const b = points[index + 1];
    return Math.atan2(b.y - a.y, b.x - a.x);
}

/**
 * Ponto mais próximo dentro da polilinha permitida.
 * `minAlong`/`maxAlong` limitam o trecho (o passo não salta para outra volta da rota).
 */
export function snapToRoute(point, points, window) {
    const metric = points && points.cumulative ? points : measurePolyline(points);
    return snapToMetric(point, metric, window);
}

export function snapToMetric(point, metric, {
    minAlong = -Infinity,
    maxAlong = Infinity
} = {} as any) {
    if (!metric || !metric.points || !metric.points.length || !point) return null;
    const px = Number(point.x);
    const py = Number(point.y);
    if (!Number.isFinite(px) || !Number.isFinite(py)) return null;
    if (metric.points.length === 1) {
        const only = metric.points[0];
        return {
            point: { x: only.x, y: only.y },
            alongM: 0,
            distance: Math.hypot(px - only.x, py - only.y),
            segmentIndex: 0
        };
    }

    let best = null;
    for (let i = 0; i < metric.points.length - 1; i += 1) {
        const start = metric.cumulative[i];
        const end = metric.cumulative[i + 1];
        if (end < minAlong - 1e-9 || start > maxAlong + 1e-9) continue;
        const proj = projectOntoSegment({ x: px, y: py }, metric.points[i], metric.points[i + 1]);
        const span = end - start;
        const along = start + span * proj.t;
        if (along < minAlong - 1e-6 || along > maxAlong + 1e-6) continue;
        if (!best || proj.distance < best.distance) {
            best = {
                point: proj.point,
                alongM: along,
                distance: proj.distance,
                segmentIndex: i
            };
        }
    }
    return best;
}

/**
 * Integrador local. `points` estão em metros do plano (x direita, y cima).
 * O heading de referência é o da polilinha; o rumo do aparelho entra relativo.
 */
export function createPositionTracker(points) {
    let metric = measurePolyline(points);
    let pose = null;
    let alongM = 0;
    let calibBearing = 0;
    let calibLocked = false;
    let referenceRad = 0;
    let ready = false;

    function headingOf(bearingDeg) {
        if (!calibLocked && Number.isFinite(bearingDeg)) {
            calibBearing = bearingDeg;
            calibLocked = true;
        }
        const bearing = Number.isFinite(bearingDeg) ? bearingDeg : calibBearing;
        const relative = relativeHeadingRad(bearing, calibBearing, referenceRad);
        return relative === null ? referenceRad : relative;
    }

    function poseAt(bearingDeg) {
        if (!ready || !pose) return null;
        return {
            point: { x: pose.x, y: pose.y },
            headingRad: headingOf(bearingDeg),
            alongM,
            remainingM: Math.max(0, metric.length - alongM),
            lengthM: metric.length
        };
    }

    function anchor({ x, y, bearingDeg, referenceRad: reference } = {} as any) {
        const snapped = snapToMetric({ x, y }, metric);
        if (!snapped) return null;
        pose = { x: snapped.point.x, y: snapped.point.y };
        alongM = snapped.alongM;
        referenceRad = Number.isFinite(reference) ? reference : tangentAt(metric, alongM);
        if (Number.isFinite(bearingDeg)) {
            calibBearing = bearingDeg;
            calibLocked = true;
        } else {
            calibBearing = 0;
            calibLocked = false;
        }
        ready = true;
        return poseAt(bearingDeg);
    }

    function applyStep(lengthM, bearingDeg) {
        if (!ready || !pose) return null;
        const length = Number(lengthM);
        if (!Number.isFinite(length) || length <= 0) return poseAt(bearingDeg);
        const heading = headingOf(bearingDeg);
        const free = {
            x: pose.x + length * Math.cos(heading),
            y: pose.y + length * Math.sin(heading)
        };
        const snapped = snapToMetric(free, metric, {
            minAlong: Math.max(0, alongM - BACK_WINDOW_M),
            maxAlong: Math.min(metric.length, alongM + length + AHEAD_SLACK_M)
        });
        if (snapped) {
            pose = { x: snapped.point.x, y: snapped.point.y };
            alongM = snapped.alongM;
        }
        return poseAt(bearingDeg);
    }

    function setPath(nextPoints) {
        metric = measurePolyline(nextPoints);
        ready = false;
        pose = null;
        alongM = 0;
    }

    return { anchor, applyStep, poseAt, setPath };
}

/** Sentido da curva no plano (y para cima). Positivo = anti-horário = esquerda. */
export function turnDirection(fromRad, toRad, thresholdDeg = TURN_THRESHOLD_DEG) {
    if (!Number.isFinite(fromRad) || !Number.isFinite(toRad)) return 'straight';
    const delta = signedDelta(radToDeg(fromRad), radToDeg(toRad));
    if (Math.abs(delta) <= thresholdDeg) return 'straight';
    return delta > 0 ? 'left' : 'right';
}

function formatMeters(distanceM) {
    return String(Math.max(0, Math.round(Number(distanceM) || 0)));
}

function destinationName(frame) {
    const segments = frame && Array.isArray(frame.segments) ? frame.segments : [];
    const last = segments[segments.length - 1];
    if (last && last.name) return last.name;
    if (frame && frame.destinationName) return frame.destinationName;
    return 'o destino';
}

/**
 * Próxima instrução a partir dos trechos da rota e da distância já andada.
 * |curva| ≤ 30° é "siga em frente". A distância vai até a próxima curva real
 * ou, se não houver, até o destino.
 */
export function nextManeuver(frame, alongM, { arrivalM = ARRIVAL_M } = {} as any) {
    const segments = (frame && Array.isArray(frame.segments) ? frame.segments : [])
        .filter((segment) => segment && Number(segment.lengthM) > 1e-6);
    const total = segments.reduce((sum, segment) => sum + Number(segment.lengthM), 0);
    const along = Math.min(total, Math.max(0, Number(alongM) || 0));
    const remaining = Math.max(0, total - along);
    const name = destinationName(frame);
    const slug = segments.length ? segments[segments.length - 1].slug : '';
    if (!segments.length || remaining <= arrivalM) {
        return {
            kind: 'arrival',
            text: `Você chegou a ${name}`,
            name,
            slug,
            distanceM: remaining
        };
    }

    let traveled = 0;
    let index = segments.length - 1;
    for (let i = 0; i < segments.length; i += 1) {
        const next = traveled + segments[i].lengthM;
        if (along < next - 1e-6 || i === segments.length - 1) {
            index = i;
            break;
        }
        traveled = next;
    }

    let distance = traveled + segments[index].lengthM - along;
    let cursor = index;
    while (cursor < segments.length - 1) {
        const incoming = Number.isFinite(segments[cursor].endHeading)
            ? segments[cursor].endHeading
            : segments[cursor].headingRad;
        const outgoing = segments[cursor + 1].headingRad;
        const direction = turnDirection(incoming, outgoing);
        if (direction !== 'straight') {
            const place = segments[cursor].name || name;
            const side = direction === 'left' ? 'esquerda' : 'direita';
            return {
                kind: direction,
                text: `Siga ${formatMeters(distance)} m e vire à ${side} em ${place}`,
                name: place,
                slug: segments[cursor].slug || '',
                distanceM: distance
            };
        }
        cursor += 1;
        if (cursor >= segments.length - 1) break;
        distance += segments[cursor].lengthM;
    }

    return {
        kind: 'straight',
        text: `Siga em frente por ${formatMeters(remaining)} m`,
        name,
        slug,
        distanceM: remaining
    };
}

function mapFrameConfig(mapConfig) {
    const src = mapConfig && mapConfig.map_config ? mapConfig.map_config : (mapConfig || {});
    const scale = Number(src.px_per_m);
    const rotation = Number(src.rotation_rad);
    if (!Number.isFinite(scale) || scale <= 0) return null;
    return {
        px_per_m: scale,
        rotation_rad: Number.isFinite(rotation) ? rotation : 0
    };
}

/**
 * Rota da T6 em metros do plano, para o integrador e para as instruções.
 * Os pontos da rota já estão em pixels; aqui voltam ao plano (y para cima).
 */
export function buildRouteFrame(route, mapConfig) {
    if (!route) return null;
    const config = mapFrameConfig(mapConfig);
    if (!config) return null;
    const origin = { pos_x_px: 0, pos_y_px: 0 };
    const plantOf = (point) => {
        if (!point) return null;
        return pixelsToMeters(
            { x: point.x != null ? point.x : point.pos_x_px, y: point.y != null ? point.y : point.pos_y_px },
            origin,
            config
        );
    };

    let raw = Array.isArray(route.points) ? route.points.map(plantOf).filter(Boolean) : [];
    if (raw.length < 2 && Array.isArray(route.edges)) {
        raw = [];
        route.edges.forEach((edge) => {
            (edge.points || []).forEach((point) => {
                const plant = plantOf(point);
                if (plant) raw.push(plant);
            });
        });
    }
    const metric = measurePolyline(raw);
    if (!metric.points.length) return null;

    const checkpoints = Array.isArray(route.checkpoints) ? route.checkpoints : [];
    const stops = checkpoints.map((checkpoint) => {
        const plant = plantOf(checkpoint);
        const snapped = plant ? snapToMetric(plant, metric) : null;
        return {
            slug: checkpoint.slug,
            name: checkpoint.name || checkpoint.label || checkpoint.slug,
            alongM: snapped ? snapped.alongM : 0,
            point: snapped ? snapped.point : plant
        };
    }).filter((stop) => stop.slug);

    const segments = [];
    for (let i = 0; i < stops.length - 1; i += 1) {
        const from = stops[i];
        const to = stops[i + 1];
        const lengthM = Math.max(0, to.alongM - from.alongM);
        if (lengthM <= 1e-6) continue;
        segments.push({
            fromSlug: from.slug,
            slug: to.slug,
            name: to.name,
            lengthM,
            headingRad: tangentAt(metric, from.alongM + Math.min(0.05, lengthM / 2)),
            endHeading: tangentAt(metric, to.alongM - Math.min(0.05, lengthM / 2))
        });
    }

    return {
        points: metric.points,
        segments,
        stops,
        lengthM: metric.length
    };
}

export function outgoingHeading(frame, slug) {
    const segments = frame && Array.isArray(frame.segments) ? frame.segments : [];
    const next = segments.find((segment) => segment.fromSlug === slug);
    if (next && Number.isFinite(next.headingRad)) return next.headingRad;
    const last = segments[segments.length - 1];
    if (!last) return 0;
    return Number.isFinite(last.endHeading) ? last.endHeading : last.headingRad;
}

/** QR num checkpoint da rota só zera a posição. Fora dela, a rota é refeita. */
export function recalibrateRoute({ route, checkpointSlug, destinationSlug, plan } = {} as any) {
    const slug = checkpointSlug == null ? '' : String(checkpointSlug);
    const stops = route && Array.isArray(route.checkpoints) ? route.checkpoints : [];
    const onRoute = stops.some((checkpoint) => checkpoint && checkpoint.slug === slug);
    if (onRoute) {
        return {
            ok: true,
            recalculated: false,
            route,
            anchorSlug: slug,
            announcement: ''
        };
    }
    if (typeof plan !== 'function') {
        return { ok: false, recalculated: false, route, anchorSlug: slug, announcement: '' };
    }
    const planned = plan({ origin: slug, destination: destinationSlug });
    if (!planned || planned.ok === false) {
        return {
            ok: false,
            recalculated: false,
            route,
            anchorSlug: slug,
            error: planned && planned.error,
            announcement: ''
        };
    }
    return {
        ok: true,
        recalculated: true,
        route: planned.route || planned,
        anchorSlug: slug,
        announcement: 'Rota recalculada'
    };
}
