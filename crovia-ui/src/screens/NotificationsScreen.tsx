import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import {
  NotificationCard,
  NotificationCategory,
  useCategoryStyle,
} from '../components/NotificationCard';
import { notifications } from '../data';
import { useTheme } from '../theme/ThemeProvider';
import { curve, hairline, radius, space, type } from '../theme/tokens';

type Filter = 'all' | NotificationCategory;

export function NotificationsScreen() {
  const { colors } = useTheme();
  const cats = useCategoryStyle();
  const [filter, setFilter] = useState<Filter>('all');

  const filters: { key: Filter; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'crowd', label: 'Warnings' },
    { key: 'haven', label: 'Havens' },
    { key: 'reroute', label: 'Routes' },
    { key: 'network', label: 'Network' },
    { key: 'reward', label: 'Rewards' },
  ];

  const list = useMemo(
    () => (filter === 'all' ? notifications : notifications.filter((n) => n.category === filter)),
    [filter],
  );

  const unread = notifications.filter((n) => n.unread).length;

  return (
    <View style={{ flex: 1, backgroundColor: colors.bgBase }}>
      <View style={styles.head}>
        <Text style={[type.displayMd, { color: colors.textPrimary }]}>Alerts</Text>
        <Text style={[type.bodySm, { color: colors.textMuted }]}>
          {unread > 0 ? `${unread} unread` : 'Nothing new'}
        </Text>
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.filters}
      >
        {filters.map((f) => {
          const on = f.key === filter;
          const tint = f.key === 'all' ? colors.accent : cats[f.key as NotificationCategory].fg;
          return (
            <Pressable
              key={f.key}
              onPress={() => setFilter(f.key)}
              accessibilityRole="button"
              accessibilityState={{ selected: on }}
              style={[
                styles.filter,
                {
                  borderColor: on ? tint : colors.borderSubtle,
                  backgroundColor: on ? colors.bgElevated : 'transparent',
                },
              ]}
            >
              <Text style={[type.label, { color: on ? colors.textPrimary : colors.textMuted }]}>
                {f.label}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>

      <ScrollView contentContainerStyle={styles.list}>
        {list.length === 0 ? (
          <View style={styles.empty}>
            <Text style={[type.h3, { color: colors.textPrimary }]}>Nothing here yet</Text>
            <Text style={[type.bodySm, { color: colors.textMuted, textAlign: 'center' }]}>
              Alerts of this kind will appear here when conditions change around you.
            </Text>
          </View>
        ) : (
          list.map((n) => <NotificationCard key={n.id} item={n} />)
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  head: { paddingHorizontal: space.xl, paddingTop: 56, paddingBottom: space.lg, gap: 4 },
  filters: { paddingHorizontal: space.xl, gap: space.sm, paddingBottom: space.lg },
  filter: {
    paddingHorizontal: 14,
    paddingVertical: 9,
    borderRadius: radius.pill,
    ...curve,
    borderWidth: hairline,
  },
  list: { padding: space.xl, paddingTop: 0, gap: space.md, paddingBottom: 40 },
  empty: { alignItems: 'center', gap: space.md, paddingVertical: 80, paddingHorizontal: space.xl },
});
