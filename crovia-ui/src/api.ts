/**
 * Talking to the CROVIA backend.
 *
 * The app keeps working when the backend is not running. That is deliberate
 * rather than lazy: the map and the geography come from the same file the
 * backend reads, so the city is always drawable, and only the live state — which
 * zones are alarming, how many people, what the agent decided — needs a server.
 * A demo should degrade to "no live data" instead of a blank screen.
 */

import {
  DistrictOverlay,
  Level,
  ZoneOverlay,
  CrowdCluster,
} from './components/CityMap.types';

const DEFAULT_BASE = 'http://localhost:8000';

// Expo replaces EXPO_PUBLIC_* at build time. Declared rather than imported from
// @types/node, because this runs in a browser and a React Native runtime, not
// in Node, and pulling Node's globals in would let server-only APIs typecheck.
declare const process: { env?: Record<string, string | undefined> } | undefined;

export const API_BASE: string =
  (typeof process !== 'undefined' && process?.env?.EXPO_PUBLIC_API_BASE) || DEFAULT_BASE;

export type ZoneVerdict = {
  zone_id: string;
  dangerous: boolean;
  reason: string;
  segment: string | null;
  segment_label: string;
  width_m: number;
  capacity_per_min: number;
  people_low: number;
  people_high: number;
  corridor_density: number;
  pinch_density: number;
  band: string;
  band_label: string;
  seconds_to_critical: number | null;
  severity: number;
  fired_by: string | null;
};

export type LiveState = {
  t: number;
  districts: Record<string, string>;
  zones: Record<string, ZoneVerdict | null>;
  unresolved: string[];
  alerts: (ZoneVerdict & { t: number })[];
  predictions: { zone_id: string; expected_inflow_per_min: number; capacity_per_min: number;
                 segment_label: string }[];
  reasoning: { t: number; kind: string; msg: string }[];
  monitored: { sentinels: number; panel: number; located: number };
  spend: { total: number; by_tier: Record<string, number> };
};

export async function fetchLiveState(signal?: AbortSignal): Promise<LiveState | null> {
  try {
    const r = await fetch(`${API_BASE}/api/state`, { signal });
    if (!r.ok) return null;
    return (await r.json()) as LiveState;
  } catch {
    return null; // backend not running: the caller falls back to demo data
  }
}

export async function stepAgent(): Promise<unknown | null> {
  try {
    const r = await fetch(`${API_BASE}/api/agent/step`, { method: 'POST' });
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

/** A zone's severity, mapped onto the map's 1-4 colour scale. */
function levelFor(v: ZoneVerdict | null): Level {
  if (!v) return 1;
  if (v.dangerous) return 4;
  if (v.severity >= 0.5) return 3;
  if (v.severity >= 0.2) return 2;
  return 1;
}

/** Turn live state into the overlays the map already knows how to draw. */
export function toOverlays(state: LiveState): {
  districts: DistrictOverlay[];
  zones: ZoneOverlay[];
  clusters: CrowdCluster[];
} {
  const zones: ZoneOverlay[] = Object.entries(state.zones).map(([id, v]) => ({
    id,
    level: levelFor(v),
    armed: !!v && (v.dangerous || v.severity >= 0.2),
  }));

  const worstByDistrict: Record<string, Level> = {};
  for (const [id, v] of Object.entries(state.zones)) {
    const d = id.startsWith('zone_stadium') ? 'district_stadium'
      : id.includes('foxhills') ? 'district_foxhills'
      : id.includes('central') ? 'district_central'
      : 'district_marina';
    const lvl = levelFor(v);
    worstByDistrict[d] = Math.max(worstByDistrict[d] ?? 1, lvl) as Level;
  }
  const districts: DistrictOverlay[] = Object.entries(state.districts).map(([id, s]) => ({
    id,
    level: (worstByDistrict[id] ?? 1) as Level,
    armed: s === 'ALERT' || s === 'WATCHING' || s === 'CONFIRMING',
  }));

  // Only alarming zones get a cluster marker. The halo is the honest
  // uncertainty, not a decorative ring.
  const clusters: CrowdCluster[] = state.alerts.slice(-3).map((a, i) => ({
    id: `alert_${i}_${a.zone_id}`,
    lat: 0,
    lon: 0,
    accuracy_m: 420,
    spread_m: 180,
    level: 4 as Level,
    label: a.segment_label,
    sampleCount: 0,
    estimate: `${Math.round(a.people_low).toLocaleString()}–${Math.round(
      a.people_high,
    ).toLocaleString()} people`,
  }));

  return { districts, zones, clusters };
}
