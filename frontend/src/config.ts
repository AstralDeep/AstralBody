/**
 * Centralized configuration for BFF and WebSocket URLs.
 * Automatically handles port redirection when running in dev/local Docker setup.
 */

export const BFF_URL = import.meta.env.VITE_BFF_URL || (
    window.location.port === "5173"
        ? `${window.location.protocol}//${window.location.hostname}:8001`
        : window.location.origin
);

export const WS_URL = (window.location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + (
    window.location.port === "5173"
        ? `${window.location.hostname}:8001`
        : window.location.host
) + '/ws';
