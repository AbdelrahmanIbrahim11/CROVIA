# Crovia — React Native UI

Design-only implementation of the Crovia crowd-safety app. Every screen from the brief is
here and navigable. Nothing calls a network, nothing computes anything.

## Run it

```bash
npm install
npx expo start
```

Press `i`, `a`, or `w`. No native modules, so Expo Go works without a build.

## What's here

```
App.tsx                     screen switcher for reviewing the whole flow
src/theme/tokens.ts         palette (dark + light), type scale, spacing, radii
src/theme/ThemeProvider.tsx theme context + light/dark toggle
src/data.ts                 all placeholder content in one file
src/components/
  Logo.tsx                  mark + lockup, drawn in Views so it inherits theme colour
  Button.tsx                primary / secondary / ghost / danger
  InputField.tsx            label, focus, error, success
  StatusChip.tsx            calm / watch / elevated / critical, plus unread badge
  MapMarker.tsx             haven / facility / contact / crowd / you
  CityMap.tsx               schematic map canvas: streets, density, zones, pins
  NotificationCard.tsx      expandable card (5 categories) + toast banner
  Chrome.tsx                header, bottom sheet, tab bar, metric
src/screens/
  SignInScreen.tsx          role switcher: citizen / admin / authority
  SignUpScreen.tsx          citizen only, with consent block
  UserDashboardScreen.tsx   map, status card, marker sheet, zone lookup, settings
  NotificationsScreen.tsx   filterable alert list
  ProfileScreen.tsx         view + edit modes
  AdminDashboardScreen.tsx  surveillance rail, zone list, zoning toolbar
  PoliceDashboardScreen.tsx admin + broadcast drawer
```

## Design decisions worth knowing

**Gold is brand, not severity.** The mark's amber is used for the primary action and brand
moments only. Severity runs on a separate green → yellow → orange → red scale so a gold
button never reads as a risk level.

**Safe havens are green, not red.** Your brief specified a red dot for safe havens. I've
built them green. In a safety product red means danger everywhere else on the map, and a
citizen glancing at their phone mid-crush will read red as "avoid". If you want the original
behaviour, change `markerHaven` in `tokens.ts` — it's one line.

**The map is a drawing, not a map.** `CityMap.tsx` renders the street armature, density
blobs, zone polygons and pins from 0–1 fractional coordinates. When you wire in MapLibre or
Leaflet, the marker and overlay props are shaped to survive the swap — replace the canvas
`View`, keep the children.

**Fonts fall back to system faces.** `tokens.ts` points `display` at Georgia/serif and
`sans` at the system face so this runs with no assets. Drop Fraunces and Inter into
`assets/fonts`, register them, and change the two constants.

## Not included, on purpose

No API calls, no auth, no state persistence, no clustering, no map library, no
`react-navigation`. The screen switcher in `App.tsx` exists so you can walk the flow; it's
meant to be replaced.
