/**
 * Wake Lock da tela durante o E4. Se o navegador não tiver a API, segue sem ela.
 */

export function createWakeLock(nav) {
    const host = nav || (typeof navigator !== 'undefined' ? navigator : null);
    let sentinel = null;
    let wanted = false;

    async function acquire() {
        wanted = true;
        const locks = host && host.wakeLock;
        if (!locks || typeof locks.request !== 'function') return false;
        if (sentinel) return true;
        try {
            sentinel = await locks.request('screen');
            if (sentinel && typeof sentinel.addEventListener === 'function') {
                sentinel.addEventListener('release', () => {
                    sentinel = null;
                });
            }
            if (!wanted && sentinel && typeof sentinel.release === 'function') {
                await sentinel.release();
                sentinel = null;
                return false;
            }
            return true;
        } catch (_) {
            sentinel = null;
            return false;
        }
    }

    async function release() {
        wanted = false;
        if (!sentinel) return;
        try {
            if (typeof sentinel.release === 'function') await sentinel.release();
        } catch (_) {
            /* a tela já pode ter soltado o lock */
        }
        sentinel = null;
    }

    return {
        acquire,
        release,
        get active() {
            return Boolean(sentinel);
        },
        get wanted() {
            return wanted;
        }
    };
}
