import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useTheme } from '../theme/ThemeProvider';
import { type } from '../theme/tokens';

import type { MarkerKind } from './CityMap.types';

/**
 * Marker shapes live in CityMap.types so both map implementations and the data
 * layer agree on one definition. Re-exported here because screens already
 * import them from this module.
 */
export type { MarkerKind, MarkerData } from './CityMap.types';

const glyphs: Record<MarkerKind, string> = {
  haven: 'H',
  facility: '+',
  contact: 'C',
  crowd: '!',
  you: '',
};

export function MapMarker({
  kind,
  active,
  onPress,
  size = 40,
}: {
  kind: MarkerKind;
  active?: boolean;
  onPress?: () => void;
  size?: number;
}) {
  const { colors } = useTheme();
  const tint = {
    haven: colors.markerHaven,
    facility: colors.markerFacility,
    contact: colors.markerContact,
    crowd: colors.markerCrowd,
    you: colors.markerYou,
  }[kind];

  const pin = size * 0.55;

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      hitSlop={8}
      style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}
    >
      <View
        style={[
          styles.halo,
          {
            width: size,
            height: size,
            borderRadius: size / 2,
            backgroundColor: tint,
            opacity: active ? 0.3 : 0.16,
          },
        ]}
      />
      <View
        style={{
          width: pin,
          height: pin,
          borderRadius: pin / 2,
          backgroundColor: tint,
          borderWidth: active ? 3 : 2.5,
          borderColor: colors.bgBase,
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {glyphs[kind] ? (
          <Text style={[type.caption, { color: colors.bgBase, fontWeight: '700' }]}>
            {glyphs[kind]}
          </Text>
        ) : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  halo: { position: 'absolute' },
});
