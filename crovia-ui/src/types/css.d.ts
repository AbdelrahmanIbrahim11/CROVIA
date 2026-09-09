// TypeScript 6 refuses a side-effect import of a stylesheet unless the module
// is declared. CityMap.web.tsx imports MapLibre's stylesheet this way, and the
// map genuinely needs it: without that CSS the map canvas is positioned wrongly
// and collapses to a few pixels tall.
declare module '*.css';
