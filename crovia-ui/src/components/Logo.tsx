import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTheme } from '../theme/ThemeProvider';
import { type } from '../theme/tokens';

/**
 * The mark is drawn rather than imported so it inherits theme colours.
 * Nine-dot grid; the bottom-right dot is enlarged and filled gold —
 * the crowd, with one point of attention resolved.
 */
export function LogoMark({ size = 44 }: { size?: number }) {
  const { colors } = useTheme();
  const s = size / 44; // tokens below are authored at 44pt

  const dot = (row: number, col: number) => (
    <View
      key={`${row}-${col}`}
      style={{
        position: 'absolute',
        width: 3.6 * s,
        height: 3.6 * s,
        borderRadius: 2 * s,
        backgroundColor: colors.textPrimary,
        left: (11 + col * 10) * s,
        top: (11 + row * 10) * s,
      }}
    />
  );

  const dots = [];
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 3; c++) {
      if (r === 2 && c === 2) continue;
      dots.push(dot(r, c));
    }
  }

  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: 12 * s,
        backgroundColor: colors.bgBase,
        borderWidth: 1.5 * s,
        borderColor: colors.accent,
      }}
    >
      {dots}
      <View
        style={{
          position: 'absolute',
          width: 11 * s,
          height: 11 * s,
          borderRadius: 6 * s,
          backgroundColor: colors.accent,
          left: 26.5 * s,
          top: 26.5 * s,
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <View
          style={{
            width: 3.6 * s,
            height: 3.6 * s,
            borderRadius: 2 * s,
            backgroundColor: colors.bgBase,
          }}
        />
      </View>
    </View>
  );
}

export function LogoLockup({ size = 44 }: { size?: number }) {
  const { colors } = useTheme();
  return (
    <View style={styles.lockup}>
      <LogoMark size={size} />
      <View>
        <Text style={[type.wordmark, { color: colors.textPrimary }]}>CROVIA</Text>
        <View style={[styles.rule, { backgroundColor: colors.accent }]} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  lockup: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  rule: { height: 1.5, marginTop: 5, width: '100%' },
});
