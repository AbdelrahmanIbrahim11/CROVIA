/**
 * Basemap source for the web map.
 *
 * Default is OpenFreeMap: real OpenStreetMap vector tiles, no API key, no
 * account, no quota. That matters for a hackathon — nothing to sign up for and
 * nothing to leak in the repo.
 *
 * OFFLINE DEMO PATH (recommended before judging — demo-room wifi is where
 * prototypes die). Cut a Lusail-only extract and serve it as a static file:
 *
 *   npm i -g pmtiles
 *   pmtiles extract https://build.protomaps.com/<latest>.pmtiles lusail.pmtiles \
 *     --bbox=51.465,25.355,51.558,25.447
 *
 * Drop the result in `assets/` and set LOCAL_PMTILES below to its URL. The
 * whole city is a few MB and the map then works with the network unplugged.
 */

export type BasemapScheme = 'dark' | 'light';

/** Set to a `pmtiles://<url>` string to run fully offline. See header. */
export const LOCAL_PMTILES: string | null = null;

const OPENFREEMAP_STYLES: Record<BasemapScheme, string> = {
  dark: 'https://tiles.openfreemap.org/styles/dark',
  light: 'https://tiles.openfreemap.org/styles/positron',
};

export function basemapStyleUrl(scheme: BasemapScheme): string {
  return OPENFREEMAP_STYLES[scheme];
}

/**
 * OpenStreetMap requires attribution and OpenFreeMap asks for credit. This is a
 * licence condition, not decoration — leave it on screen.
 */
export const ATTRIBUTION =
  '<a href="https://openfreemap.org" target="_blank" rel="noreferrer">OpenFreeMap</a> · ' +
  '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap</a>';

/**
 * Severity ramp for district fills and zone rings. Index is 1-4 to match the
 * existing `level` convention in the UI (1 calm, 4 critical).
 */
export const SEVERITY_HEX = ['#34D399', '#FBBF24', '#FB923C', '#DC2626'] as const;

export function severityColor(level: 1 | 2 | 3 | 4): string {
  return SEVERITY_HEX[level - 1];
}
