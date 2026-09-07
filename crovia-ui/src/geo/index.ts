import raw from './lusail.geo.json';

/**
 * Geography for the pilot city, plus the projection maths the map surfaces need.
 *
 * Everything in Crovia that touches place is in real lat/lon from here on. The
 * old 0-1 canvas fractions are gone: geofence circles, cluster centroids and
 * Location Retrieval fixes all arrive in lat/lon, so carrying a second
 * coordinate space next to them only creates conversion bugs.
 */

export type LatLon = { lat: number; lon: number };

/** [minLon, minLat, maxLon, maxLat] — the order MapLibre and turf both expect. */
export type BBox = [number, number, number, number];

export type City = {
  id: string;
  name: string;
  country: string;
  label: string;
  sublabel: string;
  timezone: string;
  center: LatLon;
  bbox: BBox;
  defaultZoom: number;
  minZoom: number;
  maxZoom: number;
};

/**
 * Tier 1. Big enough (1-2 km) to sit inside the CAMARA location accuracy
 * envelope, so this is the level congestion gets attributed to and the level
 * the always-on coarse geofences watch.
 */
export type District = {
  id: string;
  label: string;
  short: string;
  center: LatLon;
  radius_m: number;
  anchor: string;
  capacity_hint: number | null;
  notes: string;
};

export type ZoneKind = 'egress_gate' | 'transit' | 'pedestrian_corridor' | 'crossing';

/**
 * Tier 2. Chokepoints, not a tiling of the city — every zone here costs a
 * geofence subscription per device, so the set stays deliberately small.
 * 400 m is the practical floor before cell-level accuracy turns it to noise.
 */
export type BottleneckZone = {
  id: string;
  district_id: string;
  label: string;
  kind: ZoneKind;
  center: LatLon;
  radius_m: number;
  notes: string;
};

export type Landmark = { id: string; label: string; lat: number; lon: number };

export const city: City = raw.city as City;
export const districts: District[] = raw.districts as District[];
export const zones: BottleneckZone[] = raw.zones as BottleneckZone[];
export const landmarks: Landmark[] = raw.landmarks as Landmark[];

export const districtById: Record<string, District> = Object.fromEntries(
  districts.map((d) => [d.id, d]),
);

export const zoneById: Record<string, BottleneckZone> = Object.fromEntries(
  zones.map((z) => [z.id, z]),
);

export const zonesByDistrict: Record<string, BottleneckZone[]> = districts.reduce(
  (acc, d) => {
    acc[d.id] = zones.filter((z) => z.district_id === d.id);
    return acc;
  },
  {} as Record<string, BottleneckZone[]>,
);

const EARTH_RADIUS_M = 6_378_137;
const DEG = Math.PI / 180;

/** Great-circle distance. Used for cluster radii and "distance from you". */
export function haversineMeters(a: LatLon, b: LatLon): number {
  const dLat = (b.lat - a.lat) * DEG;
  const dLon = (b.lon - a.lon) * DEG;
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat * DEG) * Math.cos(b.lat * DEG) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(s));
}

/**
 * Web Mercator y, normalised to the unit interval by the caller. Matching
 * MapLibre's projection here means the native schematic and the real web map
 * place the same coordinate in the same relative spot.
 */
function mercatorY(lat: number): number {
  const clamped = Math.max(-85.05112878, Math.min(85.05112878, lat));
  return Math.log(Math.tan(Math.PI / 4 + (clamped * DEG) / 2));
}

export type Fraction = { x: number; y: number };

/** lat/lon to a 0-1 position inside a bbox. Backs the native schematic map. */
export function project(p: LatLon, bbox: BBox = city.bbox): Fraction {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  const yTop = mercatorY(maxLat);
  const yBottom = mercatorY(minLat);
  return {
    x: (p.lon - minLon) / (maxLon - minLon),
    y: (yTop - mercatorY(p.lat)) / (yTop - yBottom),
  };
}

/** Inverse of `project`. Turns a tap on the schematic map into a real coordinate. */
export function unproject(f: Fraction, bbox: BBox = city.bbox): LatLon {
  const [minLon, minLat, maxLon, maxLat] = bbox;
  const yTop = mercatorY(maxLat);
  const yBottom = mercatorY(minLat);
  const my = yTop - f.y * (yTop - yBottom);
  return {
    lon: minLon + f.x * (maxLon - minLon),
    lat: (2 * Math.atan(Math.exp(my)) - Math.PI / 2) / DEG,
  };
}

/**
 * How wide `meters` is as a fraction of the bbox at a given latitude. Lets the
 * schematic renderer draw a 500 m circle at its true size rather than an
 * arbitrary one — seeing how much ground 500 m actually covers is the point.
 */
export function metersToFractionX(meters: number, atLat: number, bbox: BBox = city.bbox): number {
  const [minLon, , maxLon] = bbox;
  const metersPerDegLon = 111_320 * Math.cos(atLat * DEG);
  return meters / metersPerDegLon / (maxLon - minLon);
}

/**
 * Aspect of the bbox in projected space. Mercator is conformal, so laying the
 * bbox out at this ratio keeps a geofence circle rendering as a circle instead
 * of an ellipse.
 */
export const cityProjectedAspect = (() => {
  const [minLon, minLat, maxLon, maxLat] = city.bbox;
  const w = (maxLon - minLon) * DEG;
  const h = mercatorY(maxLat) - mercatorY(minLat);
  return w / h;
})();

/** Ground metres covered by one pixel when the bbox is drawn `pxWide` wide. */
export function metersPerPixel(pxWide: number, bbox: BBox = city.bbox): number {
  const [minLon, , maxLon] = bbox;
  const widthM = 111_320 * Math.cos(city.center.lat * DEG) * (maxLon - minLon);
  return widthM / pxWide;
}

/**
 * Letterbox the bbox inside a canvas so the projection keeps its aspect. The
 * alternative — stretching to fill — silently turns every radius on screen
 * into a lie, which defeats the purpose of drawing them to scale.
 */
export function fitBBox(canvasW: number, canvasH: number) {
  const aspect = cityProjectedAspect;
  let width = canvasW;
  let height = canvasW / aspect;
  if (height > canvasH) {
    height = canvasH;
    width = canvasH * aspect;
  }
  return { x: (canvasW - width) / 2, y: (canvasH - height) / 2, width, height };
}
