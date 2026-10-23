import { signal } from '@preact/signals';

export interface VisitorPoint {
    slug: string;
    label: string;
}

export interface VisitorSession {
    origin: VisitorPoint | null;
    destination: VisitorPoint | null;
    state: string;
    returnTo: string | null;
    cameraMessage: string | null;
    announceOrigin: boolean;
}

export const visitorSession = signal<VisitorSession | null>(null);
