import React from 'react';
import { LayoutChangeEvent, StyleSheet, Text, View } from 'react-native';
import { useTheme } from '../theme/ThemeProvider';
import { curve, radius, type } from '../theme/tokens';
import { MapMarker, MarkerData } from './MapMarker';

/**
 * A schematic stand-in for the live map surface. It draws the pilot city's
 * street armature, crowd density and pins so the rest of the UI can be
 * designed and reviewed. Swap the <View> canvas for MapLibre/Leaflet later —
 * the overlay children and marker API are meant to survive that change.
 *
 * All coordinates are 0–1 fractions of the canvas so the layout holds at
 * any screen size.
 */

export type DensityBlob = {
  id: string;
  x: number;
  y: number;
  /** radius as a fraction of canvas width */
  r: number;
  /** 1 = calm, 4 = critical */
  level: 1 | 2 | 3 | 4;
};

export type Zone = {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  level: 1 | 2 | 3 | 4;
};

type Props = {
  markers?: MarkerData[];
  blobs?: DensityBlob[];
  zones?: Zone[];
  activeMarkerId?: string | null;
  onMarkerPress?: (m: MarkerData) => void;
  /** draws the admin/police measurement grid */
  showGrid?: boolean;
  children?: React.ReactNode;
};

export function CityMap({
  markers = [],
  blobs = [],
  zones = [],
  activeMarkerId,
  onMarkerPress,
  showGrid,
  children,
}: Props) {
  const { colors } = useTheme();
  const [size, setSize] = React.useState({ w: 0, h: 0 });

  const onLayout = (e: LayoutChangeEvent) => {
    const { width, height } = e.nativeEvent.layout;
    setSize({ w: width, h: height });
  };

  const densityColor = (level: number) =>
    [colors.density1, colors.density2, colors.density3, colors.density4][level - 1];

  // Street armature: fractions of the canvas.
  const roadsH = [0.22, 0.42, 0.61, 0.79];
  const roadsV = [0.18, 0.38, 0.58, 0.76, 0.92];

  return (
    <View style={[styles.canvas, { backgroundColor: colors.mapLand }]} onLayout={onLayout}>
      {/* Sea along the top edge — the pilot city is coastal */}
      <View style={[styles.water, { backgroundColor: colors.mapWater }]} />
      <Text style={[styles.waterLabel, type.caption, { color: colors.textMuted }]}>
        Mediterranean
      </Text>

      {/* City blocks */}
      {size.w > 0 &&
        roadsH.slice(0, -1).map((top, ri) =>
          roadsV.slice(0, -1).map((left, ci) => (
            <View
              key={`b-${ri}-${ci}`}
              style={{
                position: 'absolute',
                left: left * size.w + 4,
                top: top * size.h + 4,
                width: (roadsV[ci + 1] - left) * size.w - 8,
                height: (roadsH[ri + 1] - top) * size.h - 8,
                backgroundColor: colors.mapBlock,
                borderRadius: 3,
              }}
            />
          )),
        )}

      {/* Roads */}
      {size.w > 0 &&
        roadsH.map((f, i) => (
          <View
            key={`rh-${i}`}
            style={{
              position: 'absolute',
              left: 0,
              right: 0,
              top: f * size.h,
              height: i === 0 ? 6 : 3,
              backgroundColor: colors.mapRoad,
            }}
          />
        ))}
      {size.w > 0 &&
        roadsV.map((f, i) => (
          <View
            key={`rv-${i}`}
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              left: f * size.w,
              width: 3,
              backgroundColor: colors.mapRoad,
            }}
          />
        ))}

      {/* Measurement grid, admin + police only */}
      {showGrid && size.w > 0
        ? [0.2, 0.4, 0.6, 0.8].map((f) => (
            <React.Fragment key={`g-${f}`}>
              <View
                style={{
                  position: 'absolute',
                  left: 0,
                  right: 0,
                  top: f * size.h,
                  height: 1,
                  backgroundColor: colors.borderSubtle,
                  opacity: 0.5,
                }}
              />
              <View
                style={{
                  position: 'absolute',
                  top: 0,
                  bottom: 0,
                  left: f * size.w,
                  width: 1,
                  backgroundColor: colors.borderSubtle,
                  opacity: 0.5,
                }}
              />
            </React.Fragment>
          ))
        : null}

      {/* Crowd density — concentric rings stand in for a heat gradient */}
      {size.w > 0 &&
        blobs.map((b) => {
          const R = b.r * size.w;
          const tint = densityColor(b.level);
          return (
            <View key={b.id} pointerEvents="none">
              {[1, 0.68, 0.4].map((scale, i) => (
                <View
                  key={i}
                  style={{
                    position: 'absolute',
                    left: b.x * size.w - R * scale,
                    top: b.y * size.h - R * scale,
                    width: R * 2 * scale,
                    height: R * 2 * scale,
                    borderRadius: R * scale,
                    backgroundColor: tint,
                    opacity: 0.12 + i * 0.09,
                  }}
                />
              ))}
            </View>
          );
        })}

      {/* Admin zone polygons */}
      {size.w > 0 &&
        zones.map((z) => {
          const tint = densityColor(z.level);
          return (
            <View
              key={z.id}
              pointerEvents="none"
              style={{
                position: 'absolute',
                left: z.x * size.w,
                top: z.y * size.h,
                width: z.w * size.w,
                height: z.h * size.h,
                borderWidth: 1.5,
                borderColor: tint,
                borderStyle: 'dashed',
                borderRadius: radius.sm,
    ...curve,
                overflow: 'hidden',
              }}
            >
              <View
                style={[StyleSheet.absoluteFill, { backgroundColor: tint, opacity: 0.14 }]}
              />
              <Text
                style={[
                  type.caption,
                  {
                    color: colors.bgBase,
                    backgroundColor: tint,
                    alignSelf: 'flex-start',
                    paddingHorizontal: 6,
                    paddingVertical: 2,
                    borderTopLeftRadius: radius.sm - 2,
                    fontWeight: '700',
                  },
                ]}
              >
                {z.label}
              </Text>
            </View>
          );
        })}

      {/* Pins */}
      {size.w > 0 &&
        markers.map((m) => (
          <View
            key={m.id}
            style={{
              position: 'absolute',
              left: m.x * size.w - 20,
              top: m.y * size.h - 20,
            }}
          >
            <MapMarker
              kind={m.kind}
              active={activeMarkerId === m.id}
              onPress={() => onMarkerPress?.(m)}
            />
          </View>
        ))}

      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  canvas: { flex: 1, overflow: 'hidden' },
  water: { position: 'absolute', left: 0, right: 0, top: 0, height: '14%' },
  waterLabel: { position: 'absolute', top: 12, left: 16, letterSpacing: 1 },
});
