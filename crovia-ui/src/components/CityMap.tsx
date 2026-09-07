import React from 'react';
import { LayoutChangeEvent, Pressable, StyleSheet, Text, View } from 'react-native';
import { useTheme } from '../theme/ThemeProvider';
import { curve, radius as radiusToken, type } from '../theme/tokens';
import {
  city,
  districtById,
  fitBBox,
  metersPerPixel,
  project,
  unproject,
  zoneById,
} from '../geo';
import { MapMarker } from './MapMarker';
import type { CityMapProps, Level } from './CityMap.types';

export * from './CityMap.types';

/**
 * Schematic fallback used on native, where MapLibre needs a config plan build.
 * `CityMap.web.tsx` is the real map and Metro picks it automatically on web —
 * this file is the default resolution, so it also keeps `tsc` happy for the
 * screens that import from './CityMap'.
 *
 * It is schematic but no longer fictional: every circle is projected from the
 * same lat/lon in `geo/lusail.geo.json` that the backend subscribes geofences
 * against, and every radius is drawn to scale. The old version invented a
 * street grid, which looked more finished and told you less.
 */

export function CityMap({
  markers = [],
  blobs = [],
  districts = [],
  zones = [],
  clusters = [],
  activeMarkerId,
  onMarkerPress,
  onMapPress,
  showGrid,
  showDistrictLabels = true,
  children,
}: CityMapProps) {
  const { colors } = useTheme();
  const [size, setSize] = React.useState({ w: 0, h: 0 });

  const onLayout = (e: LayoutChangeEvent) => {
    const { width, height } = e.nativeEvent.layout;
    setSize({ w: width, h: height });
  };

  const fit = React.useMemo(
    () => (size.w > 0 ? fitBBox(size.w, size.h) : null),
    [size.w, size.h],
  );

  const mpp = fit ? metersPerPixel(fit.width) : 1;

  /** lat/lon to a pixel inside the letterboxed frame. */
  const toPx = React.useCallback(
    (lat: number, lon: number) => {
      if (!fit) return { x: 0, y: 0 };
      const f = project({ lat, lon });
      return { x: fit.x + f.x * fit.width, y: fit.y + f.y * fit.height };
    },
    [fit],
  );

  const densityColor = (level: Level) =>
    [colors.density1, colors.density2, colors.density3, colors.density4][level - 1];

  const handlePress = (e: any) => {
    if (!onMapPress || !fit) return;
    const { locationX, locationY } = e.nativeEvent;
    onMapPress(
      unproject({
        x: (locationX - fit.x) / fit.width,
        y: (locationY - fit.y) / fit.height,
      }),
    );
  };

  /** Absolutely-positioned circle of a true ground radius. */
  const circleStyle = (lat: number, lon: number, radiusM: number) => {
    const p = toPx(lat, lon);
    const r = radiusM / mpp;
    return { position: 'absolute' as const, left: p.x - r, top: p.y - r, width: r * 2, height: r * 2, borderRadius: r };
  };

  return (
    <Pressable style={styles.canvas} onPress={handlePress} disabled={!onMapPress}>
      <View style={[StyleSheet.absoluteFill, { backgroundColor: colors.mapLand }]} onLayout={onLayout}>
        {/* The Gulf sits east of Lusail, so the water edge is on the right. */}
        <View style={[styles.water, { backgroundColor: colors.mapWater }]} />
        <Text style={[styles.waterLabel, type.caption, { color: colors.textMuted }]}>
          ARABIAN GULF
        </Text>

        {showGrid && fit
          ? [0.2, 0.4, 0.6, 0.8].map((f) => (
              <React.Fragment key={`g-${f}`}>
                <View
                  style={{
                    position: 'absolute',
                    left: fit.x,
                    width: fit.width,
                    top: fit.y + f * fit.height,
                    height: 1,
                    backgroundColor: colors.borderSubtle,
                    opacity: 0.5,
                  }}
                />
                <View
                  style={{
                    position: 'absolute',
                    top: fit.y,
                    height: fit.height,
                    left: fit.x + f * fit.width,
                    width: 1,
                    backgroundColor: colors.borderSubtle,
                    opacity: 0.5,
                  }}
                />
              </React.Fragment>
            ))
          : null}

        {/* Tier 1 districts */}
        {fit &&
          districts.map((o) => {
            const d = districtById[o.id];
            if (!d) return null;
            const tint = densityColor(o.level);
            const p = toPx(d.center.lat, d.center.lon);
            return (
              <View key={d.id} pointerEvents="none">
                <View
                  style={[
                    circleStyle(d.center.lat, d.center.lon, d.radius_m),
                    {
                      borderWidth: o.armed ? 2 : 1,
                      borderColor: tint,
                      borderStyle: 'dashed',
                      backgroundColor: tint,
                      opacity: 0.5,
                    },
                  ]}
                />
                {showDistrictLabels ? (
                  <Text
                    style={[
                      type.caption,
                      {
                        position: 'absolute',
                        left: p.x - 50,
                        top: p.y - 8,
                        width: 100,
                        textAlign: 'center',
                        color: tint,
                        fontWeight: '700',
                        letterSpacing: 1,
                      },
                    ]}
                    numberOfLines={1}
                  >
                    {d.short.toUpperCase()}
                  </Text>
                ) : null}
              </View>
            );
          })}

        {/* Density heat */}
        {fit &&
          blobs.map((b) => {
            const tint = densityColor(b.level);
            return (
              <View key={b.id} pointerEvents="none">
                {[1, 0.66, 0.38].map((scale, i) => (
                  <View
                    key={i}
                    style={[
                      circleStyle(b.lat, b.lon, b.radius_m * scale),
                      { backgroundColor: tint, opacity: 0.1 + i * 0.08 },
                    ]}
                  />
                ))}
              </View>
            );
          })}

        {/* Tier 2 bottleneck zones */}
        {fit &&
          zones.map((o) => {
            const z = zoneById[o.id];
            if (!z) return null;
            const tint = densityColor(o.level);
            return (
              <View
                key={z.id}
                pointerEvents="none"
                style={[
                  circleStyle(z.center.lat, z.center.lon, z.radius_m),
                  {
                    borderWidth: o.armed ? 3 : 1.5,
                    borderColor: tint,
                    backgroundColor: tint,
                    opacity: 0.7,
                    ...curve,
                  },
                ]}
              />
            );
          })}

        {/* Tier 3 clusters — outer ring is real positional uncertainty */}
        {fit &&
          clusters.map((c) => {
            const tint = densityColor(c.level);
            return (
              <View key={c.id} pointerEvents="none">
                <View
                  style={[
                    circleStyle(c.lat, c.lon, c.accuracy_m),
                    { borderWidth: 1, borderColor: tint, borderStyle: 'dashed', opacity: 0.55 },
                  ]}
                />
                <View
                  style={[
                    circleStyle(c.lat, c.lon, c.spread_m),
                    { backgroundColor: tint, opacity: 0.4, borderWidth: 2, borderColor: tint },
                  ]}
                />
              </View>
            );
          })}

        {/* Pins */}
        {fit &&
          markers.map((m) => {
            const p = toPx(m.lat, m.lon);
            return (
              <View key={m.id} style={{ position: 'absolute', left: p.x - 20, top: p.y - 20 }}>
                <MapMarker
                  kind={m.kind}
                  active={activeMarkerId === m.id}
                  onPress={() => onMarkerPress?.(m)}
                />
              </View>
            );
          })}

        <Text style={[styles.schematic, type.caption, { color: colors.textMuted }]}>
          {city.label} · schematic
        </Text>

        {children}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  canvas: { flex: 1, overflow: 'hidden' },
  water: { position: 'absolute', right: 0, top: 0, bottom: 0, width: '11%' },
  waterLabel: { position: 'absolute', top: 14, right: 12, letterSpacing: 1 },
  schematic: { position: 'absolute', left: 12, bottom: 10, letterSpacing: 0.6, opacity: 0.7 },
});
