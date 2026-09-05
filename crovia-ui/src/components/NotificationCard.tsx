import React, { useState } from 'react';
import { LayoutAnimation, Platform, Pressable, StyleSheet, Text, UIManager, View } from 'react-native';
import { useTheme } from '../theme/ThemeProvider';
import { curve, elevation, hairline, radius, space, type } from '../theme/tokens';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

export type NotificationCategory =
  | 'crowd'
  | 'haven'
  | 'network'
  | 'reroute'
  | 'reward';

export type Notification = {
  id: string;
  category: NotificationCategory;
  title: string;
  summary: string;
  detail: string;
  action: string;
  time: string;
  unread?: boolean;
};

export function useCategoryStyle() {
  const { colors } = useTheme();
  return {
    crowd: { fg: colors.danger, bg: colors.dangerDim, glyph: '!', name: 'Crowd warning' },
    haven: { fg: colors.safe, bg: colors.safeDim, glyph: 'H', name: 'Safe haven' },
    network: { fg: colors.info, bg: colors.infoDim, glyph: '~', name: 'Network update' },
    reroute: { fg: colors.accent, bg: colors.accentDim, glyph: '>', name: 'Reroute' },
    reward: { fg: colors.reward, bg: colors.rewardDim, glyph: '*', name: 'Reward' },
  } as Record<NotificationCategory, { fg: string; bg: string; glyph: string; name: string }>;
}

export function NotificationCard({
  item,
  onAction,
}: {
  item: Notification;
  onAction?: (n: Notification) => void;
}) {
  const { colors } = useTheme();
  const cat = useCategoryStyle()[item.category];
  const [open, setOpen] = useState(false);

  const toggle = () => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setOpen((o) => !o);
  };

  return (
    <Pressable
      onPress={toggle}
      accessibilityRole="button"
      accessibilityState={{ expanded: open }}
      style={[
        styles.card,
        {
          backgroundColor: colors.bgSurface,
          borderColor: item.unread ? cat.fg : colors.borderSubtle,
          borderLeftWidth: item.unread ? 3 : 1,
        },
      ]}
    >
      <View style={styles.head}>
        <View style={[styles.icon, { backgroundColor: cat.bg }]}>
          <Text style={[type.h4, { color: cat.fg }]}>{cat.glyph}</Text>
        </View>

        <View style={styles.copy}>
          <View style={styles.titleRow}>
            <Text style={[type.h4, { color: colors.textPrimary, flex: 1 }]} numberOfLines={2}>
              {item.title}
            </Text>
            <Text style={[type.caption, { color: colors.textMuted }]}>{item.time}</Text>
          </View>
          <Text
            style={[type.bodySm, { color: colors.textSecondary }]}
            numberOfLines={open ? undefined : 1}
          >
            {item.summary}
          </Text>
        </View>
      </View>

      {open ? (
        <View style={styles.expanded}>
          <View style={[styles.divider, { backgroundColor: colors.borderSubtle }]} />
          <Text style={[type.bodySm, { color: colors.textSecondary }]}>{item.detail}</Text>
          <Pressable
            onPress={() => onAction?.(item)}
            accessibilityRole="button"
            style={[styles.action, { backgroundColor: cat.bg }]}
          >
            <Text style={[type.label, { color: cat.fg }]}>{item.action}</Text>
          </Pressable>
        </View>
      ) : null}
    </Pressable>
  );
}

/** Transient banner for live alerts. Design-only: parent controls visibility. */
export function Toast({
  item,
  onDismiss,
}: {
  item: Notification;
  onDismiss?: () => void;
}) {
  const { colors } = useTheme();
  const cat = useCategoryStyle()[item.category];
  return (
    <View
      style={[
        styles.toast,
        { backgroundColor: colors.bgElevated, borderColor: cat.fg },
      ]}
    >
      <View style={[styles.toastBar, { backgroundColor: cat.fg }]} />
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[type.h4, { color: colors.textPrimary }]} numberOfLines={1}>
          {item.title}
        </Text>
        <Text style={[type.bodySm, { color: colors.textSecondary }]} numberOfLines={2}>
          {item.summary}
        </Text>
      </View>
      <Pressable onPress={onDismiss} hitSlop={10} accessibilityRole="button">
        <Text style={[type.h3, { color: colors.textMuted }]}>×</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.lg,
    ...curve,
    borderWidth: hairline,
    padding: 16,
    gap: 14,
    ...elevation.low,
  },
  head: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },
  icon: {
    width: 40,
    height: 40,
    borderRadius: radius.sm,
    ...curve,
    alignItems: 'center',
    justifyContent: 'center',
  },
  copy: { flex: 1, gap: 4 },
  titleRow: { flexDirection: 'row', alignItems: 'flex-start', gap: space.sm },
  expanded: { gap: 14 },
  divider: { height: 1 },
  action: {
    alignSelf: 'flex-end',
    paddingHorizontal: 14,
    paddingVertical: 9,
    borderRadius: radius.sm,
    ...curve,
  },
  toast: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 14,
    paddingLeft: 0,
    borderRadius: radius.lg,
    ...curve,
    borderWidth: hairline,
    overflow: 'hidden',
    ...elevation.high,
  },
  toastBar: { width: 4, alignSelf: 'stretch' },
});
