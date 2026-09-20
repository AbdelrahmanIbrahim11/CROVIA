# CROVIA — the app

The React Native (Expo) front end for CROVIA. It runs on web, iOS and Android from one codebase, and it talks to the backend in [`../backend`](../backend).

For what CROVIA is and why, see the [main README](../README.md).

## Run it

```bash
npm install
npm run web          # or: npm start, then press i (iOS) / a (Android) / w (web)
```

By default it calls `http://localhost:8000`. Point it somewhere else with an environment variable:

```bash
EXPO_PUBLIC_API_BASE=https://crovia.onrender.com npm run web
```

Other useful commands:

| Command | What it does |
|---|---|
| `npm run typecheck` | TypeScript check, no build |
| `npm run build:web` | Static web build for deployment |
| `npm run sync:maplibre` | Copies the MapLibre worker out of `node_modules` (runs automatically after install) |

## The three roles

One app, three different views, chosen at sign-in:

- **Citizen** — a map of their area, their current safety status, safe places nearby, and warnings when a zone they are in becomes dangerous.
- **Operator** — the surveillance view: every watched zone, live crowd estimates, incidents to acknowledge or close, and a tool to draw a new watch zone on the map.
- **Authority** — the operator view plus a broadcast drawer for sending a warning out.

## What is here

```
App.tsx                      role-aware screen switcher
src/api.ts                   every call to the backend, in one file
src/session.ts               sign-in state and the bearer token
src/useLiveState.ts          polls /api/state and keeps the screens in step
src/push.ts                  push notification registration (expo-notifications)

src/geo/
  lusail.geo.json            THE canonical geography - districts, zones,
                             bottleneck widths, landmarks. The backend loads
                             this same file, so the two can never disagree
                             about where a street is or how wide it is.
  basemap.ts                 map style and tile source
  index.ts                   typed accessors over the geography

src/components/
  CityMap.web.tsx            the real map on web: MapLibre GL + PMTiles
  CityMap.tsx                schematic fallback map for native
  CityMap.types.ts           the prop shape both of them honour
  IncidentPanel.tsx          incident detail, acknowledge and close
  NotificationCard.tsx       expandable alert card, and the toast banner
  StatusChip.tsx             calm / watch / elevated / critical
  MapMarker.tsx              haven / facility / contact / crowd / you
  Chrome.tsx                 header, bottom sheet, tab bar, metric
  DemoCard.tsx               starts and stops a demonstration scenario
  ErrorBoundary.tsx          keeps one broken screen from taking down the app
  Button.tsx  MotionButton.tsx  InputField.tsx  Logo.tsx
  AnimatedText.tsx  AnimatedSegmentedControl.tsx

src/screens/
  SignInScreen.tsx           citizen / operator / authority
  SignUpScreen.tsx           citizen sign-up, with the consent block
  UserDashboardScreen.tsx    the citizen view
  NotificationsScreen.tsx    filterable alert list
  ProfileScreen.tsx          view and edit, consent withdrawal
  AdminDashboardScreen.tsx   the operator view
  PoliceDashboardScreen.tsx  the authority view

src/theme/
  tokens.ts                  palette (dark + light), type scale, spacing, radii
  ThemeProvider.tsx          theme context and the light/dark toggle
```

## The map

On web, [`CityMap.web.tsx`](src/components/CityMap.web.tsx) renders a real MapLibre GL map and draws zone circles, crowd density and pins on top of it. On native there is a schematic fallback in [`CityMap.tsx`](src/components/CityMap.tsx) that draws the same information from fractional 0–1 coordinates, with no map library.

Both files satisfy the same prop type in [`CityMap.types.ts`](src/components/CityMap.types.ts), so a screen does not need to know which one it got.

Map tiles come from **OpenFreeMap** — real OpenStreetMap data with no API key, no account and no quota, so there is nothing to sign up for and no secret to leak. [`basemap.ts`](src/geo/basemap.ts) also documents an offline path: cut a Lusail-only PMTiles extract of a few megabytes, set `LOCAL_PMTILES` to it, and the map keeps working with the network unplugged. Worth doing before a demo.

Zone circles never go below a minimum radius, set to 600 m in the geography file. Network positioning is accurate to hundreds of metres, so drawing a tight little circle would claim a precision the data does not have.

## Design decisions worth knowing

**Gold is brand, not severity.** The amber in the logo is used for the primary action and brand moments only. Severity runs on a separate green → yellow → orange → red scale, so a gold button never reads as a risk level.

**Safe havens are green, not red.** The original brief asked for a red dot on safe places. They are green here. Everywhere else on the map red means danger, and a person glancing at their phone in the middle of a crush will read red as "avoid" — the opposite of what a safe haven is. To go back to the brief, change `markerHaven` in [`tokens.ts`](src/theme/tokens.ts); it is one line.

**One geography file, shared with the backend.** Street widths decide when the alarm fires, so the app and the engine must read the same numbers. They both read [`src/geo/lusail.geo.json`](src/geo/lusail.geo.json).

**Fonts fall back to system faces.** `tokens.ts` points `sans` at the platform's own system font, so the app runs with no font assets to download.
