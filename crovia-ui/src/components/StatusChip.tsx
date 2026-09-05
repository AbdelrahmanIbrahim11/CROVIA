import React from 'react';
import { StyleSheet, Text, View, ViewStyle } from 'react-native';
import { useTheme } from '../theme/ThemeProvider';
import { curve, radius, type } from '../theme/tokens';

export type Level = 'calm' | 'watch' | 'elevated' | 'critical';

export const levelLabel: Record<Level, string> = {
  calm: 'Calm',
  watch: 'Watch',
  elevated: 'Elevated',
  critical: 'Critical',
};

export function useLevelColors() {
  const { colors } = useTheme();
  return {
    calm: { fg: colors.safe, bg: colors.safeDim },
    watch: { fg: colors.watch, bg: colors.watchDim },
    elevated: { fg: colors.elevated, bg: colors.elevatedDim },
    critical: { fg: colors.danger, bg: colors.dangerDim },
  } as Record<Level, { fg: string; bg: string }>;
}

export function StatusChip({
  level,
  label,
  style,
}: {
  level: Level;
  label?: string;
  style?: ViewStyle;
}) {
  const map = useLevelColors();
  const c = map[level];
  return (
    <View style={[styles.chip, { backgroundColor: c.bg }, style]}>
      <View style={[styles.dot, { backgroundColor: c.fg }]} />
      <Text style={[type.label, { color: c.fg }]}>{label ?? levelLabel[level]}</Text>
    </View>
  );
}

export function Badge({ count }: { count: number }) {
  const { colors } = useTheme();
  if (count <= 0) return null;
  return (
    <View style={[styles.badge, { backgroundColor: colors.danger }]}>
      <Text style={[type.caption, { color: '#fff', fontWeight: '700' }]}>
        {count > 9 ? '9+' : count}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    paddingLeft: 10,
    paddingRight: 12,
    paddingVertical: 6,
    borderRadius: radius.pill,
    ...curve,
    alignSelf: 'flex-start',
  },
  dot: { width: 7, height: 7, borderRadius: 4 },
  badge: {
    position: 'absolute',
    top: -4,
    right: -6,
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 4,
  },
});
