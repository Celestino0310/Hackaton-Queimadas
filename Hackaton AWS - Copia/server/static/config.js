// Runtime configuration for QueimAlerta.
//
// API_BASE controls where the frontend sends API requests.
//  - Empty string ("") = same origin that served the page (default; works when
//    you open the app from the Flask server and as a PWA installed from it).
//  - When packaging as a native app (Capacitor) the files are served from
//    the device, so you MUST point this at the machine running Flask, e.g.:
//        window.QUEIMALERTA_CONFIG = { API_BASE: "http://192.168.0.10:5000" };
//
// The value can also be overridden at runtime from the in-app Settings and is
// persisted in localStorage under "queimalerta_api_base".
window.QUEIMALERTA_CONFIG = {
  API_BASE: "",
};
