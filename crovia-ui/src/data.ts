import { DensityBlob, Zone } from './components/CityMap';
import { MarkerData } from './components/MapMarker';
import { Notification } from './components/NotificationCard';

/** Placeholder content only. Nothing here talks to a network. */

export const REGION = 'Alexandria · Corniche pilot';
export const REGION_SUB = '4 km² monitored area';

export const markers: MarkerData[] = [
  {
    id: 'you',
    kind: 'you',
    x: 0.47,
    y: 0.55,
    name: 'You are here',
    detail: 'Position sampled from the network, accurate to about 60 m.',
    distance: '—',
  },
  {
    id: 'h1',
    kind: 'haven',
    x: 0.73,
    y: 0.34,
    name: 'San Stefano Plaza',
    detail: 'Open concourse, low density, step-free access from the Corniche.',
    distance: '300 m',
  },
  {
    id: 'h2',
    kind: 'haven',
    x: 0.24,
    y: 0.7,
    name: 'Sporting Club grounds',
    detail: 'Large open ground with four gates. Currently well under capacity.',
    distance: '1.1 km',
  },
  {
    id: 'f1',
    kind: 'facility',
    x: 0.6,
    y: 0.72,
    name: 'Ambulance post 3',
    detail: 'Two crews on station. Reachable on foot in under five minutes.',
    distance: '450 m',
  },
  {
    id: 'f2',
    kind: 'facility',
    x: 0.32,
    y: 0.3,
    name: 'Raml tram exit',
    detail: 'Transit exit running normally. Useful if you need to leave the area.',
    distance: '620 m',
  },
  {
    id: 'c1',
    kind: 'contact',
    x: 0.86,
    y: 0.62,
    name: 'Police point — Stanley',
    detail: 'Staffed around the clock. Direct line available from this card.',
    distance: '900 m',
  },
  {
    id: 'x1',
    kind: 'crowd',
    x: 0.55,
    y: 0.28,
    name: 'Crowd centre',
    detail: 'Estimated 2,400 people clustered within a 200 m radius.',
    distance: '180 m',
  },
];

export const blobs: DensityBlob[] = [
  { id: 'd1', x: 0.55, y: 0.28, r: 0.26, level: 4 },
  { id: 'd2', x: 0.36, y: 0.46, r: 0.18, level: 3 },
  { id: 'd3', x: 0.78, y: 0.52, r: 0.16, level: 2 },
  { id: 'd4', x: 0.24, y: 0.74, r: 0.14, level: 1 },
];

export const zones: Zone[] = [
  { id: 'z1', x: 0.4, y: 0.16, w: 0.34, h: 0.24, label: 'Zone 7', level: 4 },
  { id: 'z2', x: 0.12, y: 0.44, w: 0.28, h: 0.2, label: 'Zone 4', level: 3 },
  { id: 'z3', x: 0.66, y: 0.58, w: 0.26, h: 0.2, label: 'Zone 11', level: 2 },
];

export const notifications: Notification[] = [
  {
    id: 'n1',
    category: 'crowd',
    title: 'Crowd building near you',
    summary: 'Danger score 78 on the Corniche at Stanley',
    detail:
      'Density between Stanley and San Stefano has crossed the alert threshold. Around 2,400 people are inside a 200 m radius and the count is still climbing.',
    action: 'View on map',
    time: '2 min',
    unread: true,
  },
  {
    id: 'n2',
    category: 'haven',
    title: 'Safe haven 300 m away',
    summary: 'San Stefano Plaza is clear and reachable on foot',
    detail:
      'San Stefano Plaza is at low density with clear access. Walking time from your position is about four minutes.',
    action: 'Get directions',
    time: '3 min',
    unread: true,
  },
  {
    id: 'n3',
    category: 'reroute',
    title: 'Take El Gaish Road instead',
    summary: 'Adds 5 minutes, avoids the congested stretch',
    detail:
      'Your usual route passes through an elevated-risk zone. El Gaish Road adds roughly five minutes but stays clear of the crowd centre.',
    action: 'Open route',
    time: '18 min',
    unread: true,
  },
  {
    id: 'n4',
    category: 'network',
    title: 'Conditions have improved',
    summary: 'Crowd thinned, priority network released',
    detail:
      'The crowd in your zone has dispersed below threshold. Your priority network slice has been released and normal service has resumed.',
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

export const zoneRows = [
  { id: 'z1', name: 'Zone 7 — Corniche / Stanley', score: 78, heads: '2,400', level: 'critical' as const },
  { id: 'z2', name: 'Zone 4 — Raml station', score: 54, heads: '1,150', level: 'elevated' as const },
  { id: 'z3', name: 'Zone 11 — San Stefano', score: 31, heads: '640', level: 'watch' as const },
  { id: 'z4', name: 'Zone 2 — Sporting', score: 12, heads: '210', level: 'calm' as const },
];
