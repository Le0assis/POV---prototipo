/** Contador de FPS só com ?perf=1. Fora disso não agenda quadro nenhum. */

export function perfEnabled(href) {
    try {
        const url = new URL(href || (typeof location === 'undefined' ? 'http://local/' : location.href));
        return url.searchParams.get('perf') === '1';
    } catch (_) {
        return false;
    }
}

export function attachPerf(map) {
    if (!map || !perfEnabled()) return null;
    const label = document.createElement('p');
    label.className = 'map-perf';
    label.setAttribute('role', 'status');
    const parent = map.getContainer().parentElement || map.getContainer();
    parent.appendChild(label);
    let frames = 0;
    let last = performance.now();
    let renderMs = 0;
    let running = true;

    function tick(now) {
        if (!running) return;
        frames += 1;
        const elapsed = now - last;
        if (elapsed >= 500) {
            const fps = Math.round((frames * 1000) / elapsed);
            label.textContent = `${fps} fps · render ${renderMs.toFixed(1)} ms`;
            frames = 0;
            last = now;
        }
        requestAnimationFrame(tick);
    }

    map.on('zoom move', () => {
        const started = performance.now();
        requestAnimationFrame(() => {
            renderMs = performance.now() - started;
        });
    });
    requestAnimationFrame(tick);
    return {
        stop() {
            running = false;
            label.remove();
        }
    };
}
