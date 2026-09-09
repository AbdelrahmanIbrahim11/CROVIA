import type {
  CrowdCluster,
  DensityBlob,
  DistrictOverlay,
  MarkerData,
  ZoneOverlay,
} from './components/CityMap.types';
import { Notification } from './components/NotificationCard';
import { city, zoneById } from './geo';

/**
 * Demo state for the Lusail pilot. Placeholder values — nothing here talks to a
 * network yet — but every coordinate is real and every id matches
 * `geo/lusail.geo.json`, so swapping this for live backend state is a data
 * change rather than a rewrite.
 *
 * Scenario: full-time at Lusail Stadium. ~89k people leaving at once, the north
 * concourse backing up into the tram link.
 */

export const REGION = city.label;
export const REGION_SUB = city.sublabel;

export const markers: MarkerData[] = [
  {
    id: 'you',
    kind: 'you',
    lat: 25.4155,
    lon: 51.497,
    name: 'You are here',
    detail:
      'Position from the network, not your handset GPS. Accurate to about 220 m in this part of Lusail.',
    distance: '—',
  },
  {
    id: 'h1',
    kind: 'haven',
    lat: 25.383,
    lon: 51.5255,
    name: 'Marina promenade deck',
    detail: 'Wide open waterfront deck, well under capacity, step-free from the Boulevard.',
    distance: '4.6 km',
  },
  {
    id: 'h2',
    kind: 'haven',
    lat: 25.428,
    lon: 51.505,
    name: 'Fox Hills open park',
    detail: 'Large open ground with four approaches. Currently calm.',
    distance: '1.6 km',
  },
  {
    id: 'f1',
    kind: 'facility',
    lat: 25.4225,
    lon: 51.4915,
    name: 'Medical post — Stadium gate 3',
    detail: 'Two crews on station for the fixture. Inside the egress fan.',
    distance: '960 m',
  },
  {
    id: 'f2',
    kind: 'facility',
    lat: 25.4113,
    lon: 51.4948,
    name: 'Lusail Tram terminus',
    detail: 'Rail link out of the precinct. Running normally, but the platform is the constraint.',
    distance: '520 m',
  },
  {
    id: 'c1',
    kind: 'contact',
    lat: 25.417,
    lon: 51.498,
    name: 'Police point — Boulevard north',
    detail: 'Staffed through the fixture. Direct line available from this card.',
    distance: '190 m',
  },
  {
    id: 'x1',
    kind: 'crowd',
    lat: 25.4242,
    lon: 51.4902,
    name: 'Crowd centre — north concourse',
    detail: 'Egress backing up against the tram link. Density still climbing.',
    distance: '1.2 km',
  },
];

export const blobs: DensityBlob[] = [
  { id: 'd1', lat: 25.424, lon: 51.4904, radius_m: 700, level: 4 },
  { id: 'd2', lat: 25.4113, lon: 51.4948, radius_m: 500, level: 3 },
  { id: 'd3', lat: 25.4157, lon: 51.4966, radius_m: 550, level: 2 },
  { id: 'd4', lat: 25.3824, lon: 51.5271, radius_m: 600, level: 1 },
];

/** Tier 1. `armed` means congestion is confirmed and coarse geofences are live. */
export const districtOverlays: DistrictOverlay[] = [
  { id: 'district_stadium', level: 4, armed: true },
  { id: 'district_foxhills', level: 2 },
  { id: 'district_central', level: 1 },
  { id: 'district_marina', level: 1 },
];

/** Tier 2. `armed` means we are currently paying for geofences on this zone. */
export const zoneOverlays: ZoneOverlay[] = [
  { id: 'zone_stadium_north_concourse', level: 4, armed: true },
  { id: 'zone_stadium_tram_link', level: 3, armed: true },
  { id: 'zone_foxhills_crossing', level: 2 },
  { id: 'zone_central_plaza_crossing', level: 1 },
  { id: 'zone_marina_promenade', level: 1 },
];

/**
 * Tier 3. Discovered, not configured. `accuracy_m` is the radius the Location
 * Retrieval API reported and is drawn as the outer halo, so the map never
 * claims more precision than the network actually gave us.
 */
export const clusters: CrowdCluster[] = [
  {
    id: 'cluster_1',
    lat: 25.4242,
    lon: 51.4902,
    accuracy_m: 420,
    spread_m: 180,
    level: 4,
    label: 'North concourse cluster',
    sampleCount: 18,
    estimate: '~2,400 — extrapolated from 18 fixes at ~3% opt-in penetration',
  },
];

export const notifications: Notification[] = [
  {
    id: 'n1',
    category: 'crowd',
    title: 'Crowd building at the stadium',
    summary: 'Danger score 78 at the north concourse',
    detail:
      'Density at the Lusail Stadium north concourse has crossed the alert threshold. 18 sampled devices cluster within 180 m and the entry rate at the tram link is still climbing.',
    action: 'View on map',
    time: '2 min',
    unread: true,
  },
  {
    id: 'n2',
    category: 'haven',
    title: 'Fox Hills is clear',
    summary: 'Open ground 1.6 km away, four approaches',
    detail:
      'Fox Hills is at low density with clear access on foot. Walking time from your position is about eighteen minutes.',
    action: 'Get directions',
    time: '3 min',
    unread: true,
  },
  {
    id: 'n3',
    category: 'reroute',
    title: 'Use the Boulevard south exit',
    summary: 'Adds 6 minutes, avoids the tram link queue',
    detail:
      'Your usual route funnels through the stadium tram link, which is accumulating faster than it clears. The Boulevard south exit adds roughly six minutes and stays out of the egress fan.',
    action: 'Open route',
    time: '18 min',
    unread: true,
  },
  {
    id: 'n4',
    category: 'network',
    title: 'Conditions have improved',
    summary: 'Crowd thinned, geofences released',
    detail:
      'Density in your district has dropped below threshold. Zone geofence subscriptions have been torn down and monitoring is back to the standing sentinel fleet.',
    action: 'Dismiss',
    time: '42 min',
  },
  {
    id: 'n5',
    category: 'reward',
    title: 'You earned 1 GB of free data',
    summary: 'For following the suggested route',
    detail:
      'Thanks for acting as a network probe and following the suggested route. 1 GB has been added to your line and expires in 30 days.',
    action: 'View rewards',
    time: '1 h',
  },
];

/** Operator table. Derived from the geo module so labels can never drift. */
export const zoneRows = [
  { id: 'zone_stadium_north_concourse', score: 78, heads: '2,400', level: 'critical' as const },
  { id: 'zone_stadium_tram_link', score: 61, heads: '1,480', level: 'elevated' as const },
  { id: 'zone_foxhills_crossing', score: 34, heads: '620', level: 'watch' as const },
  { id: 'zone_central_plaza_crossing', score: 12, heads: '210', level: 'calm' as const },
].map((r) => ({ ...r, name: zoneById[r.id]?.label ?? r.id }));
