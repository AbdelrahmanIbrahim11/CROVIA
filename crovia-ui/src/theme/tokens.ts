import { Platform, ViewStyle } from 'react-native';

/**
 * Crovia design tokens.
 * Palette derives from the brand mark: deep navy ground, cream type, warm gold
 * accent. Severity colours stay off the gold so brand and risk never collide.
 */

export const darkColors = {
  bgBase: '#131C33',
  bgSurface: '#1B2642',
  bgElevated: '#243052',
  bgInset: '#0D1425',
  scrim: 'rgba(8,12,23,0.72)',

  borderSubtle: '#2A3556',
  borderStrong: '#45527A',
  borderFocus: '#E8952A',

  textPrimary: '#EFEDE6',
  textSecondary: '#A8B0C4',
  textMuted: '#6E7893',
  textOnAccent: '#131C33',

  accent: '#E8952A',
  accentHover: '#F5A845',
  accentDim: '#3F2D15',

  safe: '#34D399',
  safeDim: '#12362C',
  watch: '#FBBF24',
  watchDim: '#443212',
  elevated: '#FB923C',
  elevatedDim: '#4A2A14',
  danger: '#F87171',
  dangerDim: '#451B1B',
  critical: '#DC2626',
  info: '#60A5FA',
  infoDim: '#16294A',
  reward: '#A78BFA',
  rewardDim: '#2A2149',

  density1: '#34D399',
  density2: '#FBBF24',
  density3: '#FB923C',
  density4: '#DC2626',

  markerHaven: '#34D399',
  markerContact: '#60A5FA',
  markerFacility: '#A78BFA',
  markerCrowd: '#DC2626',
  markerYou: '#E8952A',

  mapLand: '#182242',
  mapBlock: '#1E2A4C',
  mapRoad: '#2B3760',
  mapWater: '#0E1730',
};

export const lightColors: typeof darkColors = {
  bgBase: '#F2F0EA',
  bgSurface: '#FFFFFF',
  bgElevated: '#FBFAF6',
  bgInset: '#EAE7DE',
  scrim: 'rgba(58,54,48,0.5)',

  borderSubtle: '#E0DCD0',
  borderStrong: '#B4AE9C',
  borderFocus: '#C97B14',

  textPrimary: '#131C33',
  textSecondary: '#4A5470',
  textMuted: '#8A91A3',
  textOnAccent: '#FFFFFF',

  accent: '#C97B14',
  accentHover: '#E8952A',
  accentDim: '#FAEEDA',

  safe: '#059669',
  safeDim: '#DFF4EA',
  watch: '#B45309',
  watchDim: '#FCF2DC',
  elevated: '#C2410C',
  elevatedDim: '#FCE7DA',
  danger: '#DC2626',
  dangerDim: '#FCE6E6',
  critical: '#991B1B',
  info: '#2563EB',
  infoDim: '#E3EDFD',
  reward: '#7C3AED',
  rewardDim: '#EEE8FD',

  density1: '#059669',
  density2: '#D97706',
  density3: '#EA580C',
  density4: '#DC2626',

  markerHaven: '#059669',
  markerContact: '#2563EB',
  markerFacility: '#7C3AED',
  markerCrowd: '#DC2626',
  markerYou: '#C97B14',

  mapLand: '#E8E4D8',
  mapBlock: '#DEDACC',
  mapRoad: '#F7F5EF',
  mapWater: '#CFE0DC',
};

export type Colors = typeof darkColors;

/**
 * One family throughout. On iOS 'System' resolves to SF Pro, which switches to
 * its Display optical size above 20pt by itself — that shift is where most of
 * the considered feel comes from, so we let it work rather than introducing a
 * second face.
 *
 * To use Inter instead: drop the .ttf files in assets/fonts, register them,
 * and change `sans` below.
 */
export const fonts = {
  sans: Platform.select({ ios: 'System', android: 'sans-serif', default: 'System' })!,
};

const f = fonts.sans;

/**
 * Tracking follows SF's optical curve — tighter as type grows, opening back up
 * below 15pt so small text stays legible. Values in points.
 */
export const type = {
  displayLg: { fontFamily: f, fontSize: 36, lineHeight: 42, fontWeight: '700' as const, letterSpacing: -0.9 },
  displayMd: { fontFamily: f, fontSize: 28, lineHeight: 34, fontWeight: '700' as const, letterSpacing: -0.6 },

  h1: { fontFamily: f, fontSize: 24, lineHeight: 30, fontWeight: '700' as const, letterSpacing: -0.5 },
  h2: { fontFamily: f, fontSize: 20, lineHeight: 25, fontWeight: '600' as const, letterSpacing: -0.4 },
  h3: { fontFamily: f, fontSize: 17, lineHeight: 22, fontWeight: '600' as const, letterSpacing: -0.3 },
  h4: { fontFamily: f, fontSize: 15, lineHeight: 20, fontWeight: '600' as const, letterSpacing: -0.2 },

  body: { fontFamily: f, fontSize: 16, lineHeight: 23, letterSpacing: -0.2 },
  bodySm: { fontFamily: f, fontSize: 14, lineHeight: 20, letterSpacing: -0.1 },
  label: { fontFamily: f, fontSize: 13, lineHeight: 18, fontWeight: '500' as const },
  caption: { fontFamily: f, fontSize: 12, lineHeight: 16 },

  metricLg: { fontFamily: f, fontSize: 36, lineHeight: 40, fontWeight: '700' as const, letterSpacing: -1.4 },
  metricMd: { fontFamily: f, fontSize: 22, lineHeight: 26, fontWeight: '700' as const, letterSpacing: -0.7 },

  button: { fontFamily: f, fontSize: 16, lineHeight: 21, fontWeight: '600' as const, letterSpacing: -0.2 },

  /** Brand only. The wide tracking belongs to the wordmark, not the interface. */
  wordmark: { fontFamily: f, fontSize: 20, lineHeight: 24, fontWeight: '700' as const, letterSpacing: 3.4 },
};

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 28, xxxl: 40 };

/**
 * Radius carries hierarchy: the larger the surface, the rounder its corner.
 * One radius on everything is the flattest-looking mistake in app UI.
 */
export const radius = {
  xs: 8,
  sm: 12,
  md: 16,
  lg: 22,
  xl: 32,
  pill: 999,
};

/** iOS squircle. Degrades to a normal arc on Android. */
export const curve: ViewStyle = Platform.select({
  ios: { borderCurve: 'continuous' } as ViewStyle,
  default: {},
})!;

/** Depth rather than outlines — Apple leans on shadow, not 1px borders. */
export const elevation = {
  low: Platform.select({
    ios: {
      shadowColor: '#000',
      shadowOpacity: 0.14,
      shadowRadius: 12,
      shadowOffset: { width: 0, height: 4 },
    },
    android: { elevation: 3 },
    default: {},
  })!,
  high: Platform.select({
    ios: {
      shadowColor: '#000',
      shadowOpacity: 0.24,
      shadowRadius: 28,
      shadowOffset: { width: 0, height: 12 },
    },
    android: { elevation: 12 },
    default: {},
  })!,
};

/** 1px reads heavy at 3x. */
export const hairline = Platform.OS === 'ios' ? 0.5 : 1;
