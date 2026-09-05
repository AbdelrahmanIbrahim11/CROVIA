import React from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { useTheme } from '../theme/ThemeProvider';
import { curve, elevation, hairline, radius, space, type } from '../theme/tokens';
import { LogoMark } from './Logo';
import { Badge } from './StatusChip';

export function AppHeader({
  region,
  subtitle,
  unread = 0,
  onBell,
  onSettings,
}: {
  region: string;
  subtitle?: string;
  unread?: number;
  onBell?: () => void;
  onSettings?: () => void;
}) {
  const { colors } = useTheme();
  return (
    <View
      style={[
        styles.header,
        { backgroundColor: colors.bgBase, borderBottomColor: colors.borderSubtle },
      ]}
    >
      <LogoMark size={34} />
      <View style={{ flex: 1 }}>
        <Text style={[type.h3, { color: colors.textPrimary }]} numberOfLines={1}>
          {region}
        </Text>
        {subtitle ? (
          <Text style={[type.caption, { color: colors.textMuted }]} numberOfLines={1}>
            {subtitle}
          </Text>
        ) : null}
      </View>

      <Pressable onPress={onBell} hitSlop={10} accessibilityRole="button" accessibilityLabel="Alerts">
        <View style={[styles.iconBtn, { borderColor: colors.borderSubtle }]}>
          <Text style={{ fontSize: 16, color: colors.textPrimary }}>◔</Text>
          <Badge count={unread} />
        </View>
      </Pressable>

      <Pressable onPress={onSettings} hitSlop={10} accessibilityRole="button" accessibilityLabel="Settings">
        <View style={[styles.iconBtn, { borderColor: colors.borderSubtle }]}>
          <Text style={{ fontSize: 16, color: colors.textPrimary }}>⋯</Text>
        </View>
      </Pressable>
    </View>
  );
}

/** Bottom sheet used for marker detail, settings and the zone query form. */
export function Sheet({
  visible,
  title,
  onClose,
  children,
}: {
  visible: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const { colors } = useTheme();
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.scrim, { backgroundColor: colors.scrim }]} onPress={onClose} />
      <View
        style={[
          styles.sheet,
          { backgroundColor: colors.bgSurface, borderColor: colors.borderSubtle },
        ]}
      >
        <View style={[styles.grabber, { backgroundColor: colors.borderStrong }]} />
        <View style={styles.sheetHead}>
          <Text style={[type.h2, { color: colors.textPrimary, flex: 1 }]}>{title}</Text>
          <Pressable onPress={onClose} hitSlop={10} accessibilityRole="button">
            <Text style={[type.h2, { color: colors.textMuted }]}>×</Text>
          </Pressable>
        </View>
        {children}
      </View>
    </Modal>
  );
}

export type TabKey = 'map' | 'alerts' | 'profile';

export function TabBar({
  active,
  unread = 0,
  onChange,
}: {
  active: TabKey;
  unread?: number;
  onChange: (k: TabKey) => void;
}) {
  const { colors } = useTheme();
  const tabs: { key: TabKey; label: string; glyph: string }[] = [
    { key: 'map', label: 'Map', glyph: '◈' },
    { key: 'alerts', label: 'Alerts', glyph: '◔' },
    { key: 'profile', label: 'Profile', glyph: '◐' },
  ];

  return (
    <View
      style={[styles.tabs, { backgroundColor: colors.bgBase, borderTopColor: colors.borderSubtle }]}
    >
      {tabs.map((t) => {
        const on = t.key === active;
        return (
          <Pressable
            key={t.key}
            onPress={() => onChange(t.key)}
            accessibilityRole="tab"
            accessibilityState={{ selected: on }}
            style={styles.tab}
          >
            <View>
              <Text style={{ fontSize: 18, color: on ? colors.accent : colors.textMuted }}>
                {t.glyph}
              </Text>
              {t.key === 'alerts' ? <Badge count={unread} /> : null}
            </View>
            <Text style={[type.caption, { color: on ? colors.accent : colors.textMuted }]}>
              {t.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

/** Small labelled figure used in the admin and police data rails. */
export function Metric({
  value,
  label,
  tint,
}: {
  value: string;
  label: string;
  tint?: string;
}) {
  const { colors } = useTheme();
  return (
    <View style={{ gap: 2, flex: 1 }}>
      <Text style={[type.metricMd, { color: tint ?? colors.textPrimary }]}>{value}</Text>
      <Text style={[type.caption, { color: colors.textMuted }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingHorizontal: space.xl,
    paddingVertical: 14,
    borderBottomWidth: hairline,
  },
  iconBtn: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    borderWidth: hairline,
    alignItems: 'center',
    justifyContent: 'center',
  },
  scrim: { ...StyleSheet.absoluteFill },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    borderCurve: 'continuous',
    borderWidth: 0,
    ...elevation.high,
    padding: space.xl,
    paddingBottom: space.xxl,
    gap: space.lg,
  },
  grabber: {
    width: 40,
    height: 4,
    borderRadius: 2,
    alignSelf: 'center',
    marginTop: -8,
    marginBottom: 4,
  },
  sheetHead: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  tabs: { flexDirection: 'row', borderTopWidth: hairline, paddingTop: 10, paddingBottom: 24 },
  tab: { flex: 1, alignItems: 'center', gap: 4 },
});
