import type { LatLon } from '../geo';

/**
 * The shared contract between the two CityMap implementations (MapLibre on web,
 * schematic on native). Both render the same props, so screens never care which
 * one they got.
 */

/** 1 calm, 2 watch, 3 elevated, 4 critical. */
export type Level = 1 | 2 | 3 | 4;

export type MarkerKind = 'haven' | 'facility' | 'contact' | 'crowd' | 'you';

export type MarkerData = {
  id: string;
  kind: MarkerKind;
  lat: number;
  lon: number;
  name: string;
  detail: string;
  distance: string;
};

/** Heat contribution, sized in real metres rather than canvas fractions. */
export type DensityBlob = {
  id: string;
  lat: number;
  lon: number;
  radius_m: number;
  level: Level;
};

/**
 * Live state for a Tier 1 district. Geometry comes from the geo module by id —
 * only the state travels, so the map and the backend can never disagree about
 * where a district is.
 */
export type DistrictOverlay = {
  id: string;
  level: Level;
  /** Congestion confirmed here; coarse geofences are live. */
  armed?: boolean;
};

/** Live state for a Tier 2 bottleneck zone. Geometry comes from the geo module. */
export type ZoneOverlay = {
  id: string;
  level: Level;
  /** Zone geofence subscriptions are currently paid for and running. */
  armed?: boolean;
};

/**
 * Tier 3 — the red dot. Not a place we defined in advance: this is a cluster
 * discovered by running DBSCAN over Location Retrieval fixes.
 */
export type CrowdCluster = {
  id: string;
  lat: number;
  lon: number;
  /**
   * Positional uncertainty, taken from the `radius` the Location Retrieval API
   * returns. Drawn as the outer halo. Showing it honestly is the point — a
   * cluster known to +/- 800 m must not look like a pin dropped on a doorway.
   */
  accuracy_m: number;
  /** Spatial extent of the cluster itself, from the spread of member fixes. */
  spread_m: number;
  level: Level;
  label: string;
  /** How many device fixes this cluster was built from. */
  sampleCount: number;
  /** Optional headcount estimate. Always state the extrapolation alongside it. */
  estimate?: string;
};

export type CityMapProps = {
  markers?: MarkerData[];
  blobs?: DensityBlob[];
  districts?: DistrictOverlay[];
  zones?: ZoneOverlay[];
  clusters?: CrowdCluster[];
  activeMarkerId?: string | null;
  onMarkerPress?: (m: MarkerData) => void;
  /** Tap-to-place. Backs the operator pin and the "simulate crowd here" tool. */
  onMapPress?: (p: LatLon) => void;
  /** Admin and police measurement grid. */
  showGrid?: boolean;
  showDistrictLabels?: boolean;
  children?: React.ReactNode;
};
