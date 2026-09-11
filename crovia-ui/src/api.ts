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
import { bottleneckOf, segmentPath, zoneById } from './geo';
import { authHeader } from './session';

const DEFAULT_BASE = 'http://localhost:8000';

// Expo replaces EXPO_PUBLIC_* at build time. Declared rather than imported from
// @types/node, because this runs in a browser and a React Native runtime, not
// in Node, and pulling Node's globals in would let server-only APIs typecheck.
declare const process: { env?: Record<string, string | undefined> } | undefined;

/**
 * Where the backend is.
 *
 * EXPO_PUBLIC_API_BASE wins if it is set. Otherwise the address is worked out
 * from the page itself: whatever host served the app, on port 8000.
 *
 * Hard-coding localhost broke the app whenever it was opened at anything other
 * than localhost - a phone on the same wifi reaching 192.168.x.x, for example,
 * would ask its OWN localhost for the backend, find nothing, and report that
 * CROVIA was unreachable when the service was running perfectly.
 */
function resolveApiBase(): string {
  const configured =
    typeof process !== 'undefined' ? process?.env?.EXPO_PUBLIC_API_BASE : undefined;
  if (configured) return configured;

  // Web: follow the host the page came from. Native has no window.location,
  // so it falls back to localhost, which is right for a simulator.
  if (typeof window !== 'undefined' && window.location?.hostname) {
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:8000`;
  }
  return DEFAULT_BASE;
}

export const API_BASE: string = resolveApiBase();

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
    // The live picture is operations data and now needs a token. Without one
    // the backend answers 401 and the app falls back to demo data, exactly as
    // it does when the backend is not running at all.
    const r = await fetch(`${API_BASE}/api/state`, { signal, headers: authHeader() });
    if (!r.ok) return null;
    return (await r.json()) as LiveState;
  } catch {
    return null; // backend not running: the caller falls back to demo data
  }
}

export async function stepAgent(): Promise<unknown | null> {
  try {
    const r = await fetch(`${API_BASE}/api/agent/step`, {
      method: 'POST',
      headers: authHeader(),
    });
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

export type Incident = {
  id: string;
  zone_id: string;
  segment_id: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_s: number | null;
  open: boolean;
  acknowledged: boolean;
  acknowledged_by: string | null;
  closed_by: string | null;
  action_taken: string | null;
  people_low: number | null;
  people_high: number | null;
  fired_by: string | null;
  reason: string | null;
};

export async function fetchIncidents(): Promise<Incident[]> {
  try {
    const r = await fetch(`${API_BASE}/api/incidents`, { headers: authHeader() });
    if (!r.ok) return [];
    return ((await r.json()).incidents ?? []) as Incident[];
  } catch {
    return [];
  }
}

/** Say a named person has seen this alarm. Authority accounts only. */
export async function acknowledgeIncident(id: string): Promise<Incident | null> {
  return incidentAction(`${API_BASE}/api/incidents/${id}/acknowledge`, {});
}

/** Close an incident and record what was done about it. Authority only. */
export async function closeIncident(
  id: string,
  actionTaken: string,
): Promise<Incident | null> {
  return incidentAction(`${API_BASE}/api/incidents/${id}/close`, {
    action_taken: actionTaken,
  });
}

async function incidentAction(url: string, body: unknown): Promise<Incident | null> {
  try {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify(body),
    });
    return r.ok ? ((await r.json()) as Incident) : null;
  } catch {
    return null;
  }
}

/** What a citizen is allowed to see: severities and their own warnings. */
export type NearbyState = {
  t: number;
  zones: Record<string, {
    zone_id: string;
    dangerous: boolean;
    severity: number;
    segment_label: string;
    band_label: string;
  } | null>;
  districts: Record<string, string>;
  alerts: { zone_id: string; segment_label: string; reason: string; t: number }[];
  my_warnings: Warning[];
  monitored: boolean;
};

export async function fetchNearby(signal?: AbortSignal): Promise<NearbyState | null> {
  try {
    const r = await fetch(`${API_BASE}/api/nearby`, { signal, headers: authHeader() });
    if (!r.ok) return null;
    return (await r.json()) as NearbyState;
  } catch {
    return null;
  }
}

export type Warning = {
  id: string;
  zone_id: string;
  title: string;
  body: string;
  sent_at: string | null;
  read: boolean;
};

/** The warnings sent to the person signed in. They cannot ask for anyone else's. */
export async function fetchMyWarnings(): Promise<Warning[]> {
  try {
    const r = await fetch(`${API_BASE}/api/warnings/me`, { headers: authHeader() });
    if (!r.ok) return [];
    return ((await r.json()).warnings ?? []) as Warning[];
  } catch {
    return [];
  }
}

export type OperatorZone = {
  zone_id: string;
  label: string;
  district_id: string;
  lat: number;
  lon: number;
  radius_m: number;
  width_m: number;
  length_m: number;
  capacity_per_min?: number;
  max_safe_people?: number;
};

/**
 * Add a zone an operator drew.
 *
 * width_m and length_m are not optional. The danger rule starts from the
 * narrowest link, so a circle without one cannot be judged, and the backend
 * refuses anything under 600 m because below that the network cannot resolve
 * the circle reliably. The error text comes back from the server and is worth
 * showing verbatim: it explains the refusal.
 */
export async function createOperatorZone(
  z: Omit<OperatorZone, 'zone_id' | 'capacity_per_min' | 'max_safe_people'> & {
    created_by?: string;
  },
): Promise<{ ok: true; zone: OperatorZone } | { ok: false; error: string }> {
  try {
    const r = await fetch(`${API_BASE}/api/zones/operator`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify(z),
    });
    const body = await r.json();
    if (!r.ok) return { ok: false, error: body?.detail ?? 'Could not add the zone.' };
    return { ok: true, zone: body as OperatorZone };
  } catch {
    return { ok: false, error: 'The CROVIA service is not reachable.' };
  }
}

export async function deleteOperatorZone(zoneId: string): Promise<boolean> {
  try {
    const r = await fetch(`${API_BASE}/api/zones/operator/${zoneId}`, {
      method: 'DELETE',
      headers: authHeader(),
    });
    return r.ok;
  } catch {
    return false;
  }
}

export async function markWarningRead(id: string): Promise<boolean> {
  try {
    const r = await fetch(`${API_BASE}/api/warnings/${id}/read`, {
      method: 'POST',
      headers: authHeader(),
    });
    return r.ok;
  } catch {
    return false;
  }
}

export type ConsentState = {
  monitored: boolean;
  phone_number?: string;
  granted_at?: string | null;
  revoked_at?: string | null;
};

/** Whether CROVIA is watching the person signed in. They can always ask. */
export async function fetchMyConsent(): Promise<ConsentState | null> {
  try {
    const r = await fetch(`${API_BASE}/api/consent/me`, { headers: authHeader() });
    return r.ok ? ((await r.json()) as ConsentState) : null;
  } catch {
    return null;
  }
}

/**
 * Turn monitoring on or off for the person signed in.
 *
 * The backend refuses any number that is not their own, so passing the number
 * here cannot be used to change somebody else's setting.
 */
export async function setMyConsent(
  phoneNumber: string,
  on: boolean,
): Promise<boolean> {
  try {
    const r = await fetch(`${API_BASE}/api/consent`, {
      method: on ? 'POST' : 'DELETE',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify({ phone_number: phoneNumber }),
    });
    return r.ok;
  } catch {
    return false;
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

  // A district shows the colour of its worst zone. The mapping comes from the
  // geography file rather than from guessing at the zone id: reading the
  // district out of the name broke silently the moment a zone was renamed, and
  // it is already recorded properly one lookup away.
  const worstByDistrict: Record<string, Level> = {};
  for (const [id, v] of Object.entries(state.zones)) {
    const d = zoneById[id]?.district_id;
    if (!d) continue;
    const lvl = levelFor(v);
    worstByDistrict[d] = Math.max(worstByDistrict[d] ?? 1, lvl) as Level;
  }
  const districts: DistrictOverlay[] = Object.entries(state.districts).map(([id, s]) => ({
    id,
    level: (worstByDistrict[id] ?? 1) as Level,
    armed: s === 'ALERT' || s === 'WATCHING' || s === 'CONFIRMING',
  }));

  // Only alarming zones get a cluster marker, and it is drawn on the hazard
  // itself rather than on the middle of the zone. A 600 m circle is wide enough
  // that its centre can sit a few hundred metres from the ramp that is actually
  // failing, and an operator sent to the wrong end of a concourse has been sent
  // to the wrong place.
  //
  // These previously carried latitude and longitude of zero, which put every
  // alarm in the Atlantic instead of on Lusail.
  const clusters: CrowdCluster[] = state.alerts
    .slice(-3)
    .map((a, i): CrowdCluster | null => {
      const zone = zoneById[a.zone_id];
      if (!zone) return null;
      const hazard = bottleneckOf(a.zone_id);
      const path = hazard ? segmentPath(a.zone_id, hazard) : [];
      // Midpoint of the narrow link, falling back to the zone centre.
      const at = path.length ? path[Math.floor(path.length / 2)] : zone.center;
      return {
        id: `alert_${i}_${a.zone_id}`,
        lat: at.lat,
        lon: at.lon,
        // The halo is the honest uncertainty, not a decorative ring. Network
        // positioning resolves to a few hundred metres, so a crisp dot would
        // claim a precision the network cannot deliver.
        accuracy_m: 420,
        // How far the crowd itself reaches: the length of the failing link.
        spread_m: hazard ? Math.max(120, hazard.width_m * 20) : 180,
        level: 4 as Level,
        label: a.segment_label,
        sampleCount: 0,
        estimate: `${Math.round(a.people_low).toLocaleString()}–${Math.round(
          a.people_high,
        ).toLocaleString()} people`,
      };
    })
    .filter((c): c is CrowdCluster => c !== null);

  return { districts, zones, clusters };
}
