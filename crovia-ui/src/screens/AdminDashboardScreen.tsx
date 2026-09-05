import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Button } from '../components/Button';
import { AppHeader, Metric, Sheet } from '../components/Chrome';
import { CityMap } from '../components/CityMap';
import { StatusChip, useLevelColors } from '../components/StatusChip';
import { blobs, markers, REGION, zoneRows, zones } from '../data';
import { useTheme } from '../theme/ThemeProvider';
import { curve, hairline, radius, space, type } from '../theme/tokens';

type Tool = null | 'draw' | 'reroute' | 'measure';

export function AdminDashboardScreen({
  onSignOut,
  extraToolbar,
  roleLabel = 'Surveillance',
}: {
  onSignOut: () => void;
  extraToolbar?: React.ReactNode;
  roleLabel?: string;
}) {
  const { colors } = useTheme();
  const levels = useLevelColors();
  const [tool, setTool] = useState<Tool>(null);
  const [railOpen, setRailOpen] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const tools: { key: Exclude<Tool, null>; label: string; glyph: string }[] = [
    { key: 'draw', label: 'Draw zone', glyph: '▱' },
    { key: 'reroute', label: 'Reroute', glyph: '⤳' },
    { key: 'measure', label: 'Measure', glyph: '⇔' },
  ];

  return (
    <View style={{ flex: 1, backgroundColor: colors.bgBase }}>
      <AppHeader
        region={REGION}
        subtitle={`${roleLabel} · 4 zones monitored`}
        unread={3}
        onSettings={() => setSettingsOpen(true)}
      />

      <View style={{ flex: 1 }}>
        <CityMap markers={markers} blobs={blobs} zones={zones} showGrid>
          {/* Editor toolbar */}
          <View
            style={[
              styles.toolbar,
              { backgroundColor: colors.bgSurface, borderColor: colors.borderSubtle },
            ]}
          >
            {tools.map((t) => {
              const on = tool === t.key;
              return (
                <Pressable
                  key={t.key}
                  onPress={() => setTool(on ? null : t.key)}
                  accessibilityRole="button"
                  accessibilityState={{ selected: on }}
                  style={[
                    styles.tool,
                    on && { backgroundColor: colors.accentDim, borderColor: colors.accent },
                  ]}
                >
                  <Text style={{ fontSize: 17, color: on ? colors.accent : colors.textSecondary }}>
                    {t.glyph}
                  </Text>
                </Pressable>
              );
            })}
            {extraToolbar}
          </View>

          {tool ? (
            <View style={[styles.toolHint, { backgroundColor: colors.accentDim, borderColor: colors.accent }]}>
              <Text style={[type.bodySm, { color: colors.accent }]}>
                {tool === 'draw'
                  ? 'Tap the map to place polygon corners. Double-tap to close the zone.'
                  : tool === 'reroute'
                  ? 'Drag from a congested zone to the destination you want people sent towards.'
                  : 'Tap two points to measure the distance between them.'}
              </Text>
            </View>
          ) : null}
        </CityMap>

        {/* Data rail */}
        <View
          style={[
            styles.rail,
            {
              backgroundColor: colors.bgSurface,
              borderColor: colors.borderSubtle,
              maxHeight: railOpen ? '58%' : 66,
            },
          ]}
        >
          <Pressable onPress={() => setRailOpen((o) => !o)} style={styles.railHead} accessibilityRole="button">
            <Text style={[type.h3, { color: colors.textPrimary, flex: 1 }]}>Active regions</Text>
            <StatusChip level="critical" label="1 critical" />
            <Text style={[type.h3, { color: colors.textMuted }]}>{railOpen ? '⌄' : '⌃'}</Text>
          </Pressable>

          {railOpen ? (
            <>
              <View style={[styles.metrics, { borderColor: colors.borderSubtle }]}>
                <Metric value="78" label="Peak danger score" tint={colors.danger} />
                <Metric value="4,400" label="People tracked" />
                <Metric value="12" label="Probes active" tint={colors.info} />
              </View>

              <ScrollView contentContainerStyle={styles.zoneList}>
                {zoneRows.map((z) => (
                  <Pressable
                    key={z.id}
                    accessibilityRole="button"
                    style={[styles.zoneRow, { borderColor: colors.borderSubtle }]}
                  >
                    <View style={[styles.scorePill, { backgroundColor: levels[z.level].bg }]}>
                      <Text style={[type.metricMd, { color: levels[z.level].fg }]}>{z.score}</Text>
                    </View>
                    <View style={{ flex: 1, gap: 2 }}>
                      <Text style={[type.h4, { color: colors.textPrimary }]} numberOfLines={1}>
                        {z.name}
                      </Text>
                      <Text style={[type.caption, { color: colors.textMuted }]}>
                        {z.heads} people in zone
                      </Text>
                    </View>
                    <StatusChip level={z.level} />
                  </Pressable>
                ))}
              </ScrollView>
            </>
          ) : null}
        </View>
      </View>

      <Sheet visible={settingsOpen} title="Settings" onClose={() => setSettingsOpen(false)}>
        <Text style={[type.bodySm, { color: colors.textSecondary }]}>
          Signed in as an operations account for the Alexandria pilot.
        </Text>
        <Button
          label="Sign out"
          variant="secondary"
          full
          onPress={() => {
            setSettingsOpen(false);
            onSignOut();
          }}
        />
      </Sheet>
    </View>
  );
}

const styles = StyleSheet.create({
  toolbar: {
    position: 'absolute',
    top: space.lg,
    right: space.lg,
    borderWidth: hairline,
    borderRadius: radius.md,
    ...curve,
    padding: 5,
    gap: 5,
  },
  tool: {
    width: 42,
    height: 42,
    borderRadius: radius.sm,
    ...curve,
    borderWidth: hairline,
    borderColor: 'transparent',
    alignItems: 'center',
    justifyContent: 'center',
  },
  toolHint: {
    position: 'absolute',
    top: space.lg,
    left: space.lg,
    right: 80,
    borderWidth: hairline,
    borderRadius: radius.md,
    ...curve,
    padding: space.md,
  },
  rail: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    borderTopWidth: hairline,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    paddingHorizontal: space.lg,
    paddingTop: space.lg,
    paddingBottom: space.xl,
  },
  railHead: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingBottom: space.md },
  metrics: {
    flexDirection: 'row',
    gap: space.md,
    borderTopWidth: hairline,
    borderBottomWidth: hairline,
    paddingVertical: space.md,
  },
  zoneList: { gap: space.sm, paddingTop: space.md, paddingBottom: space.lg },
  zoneRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    borderWidth: hairline,
    borderRadius: radius.md,
    ...curve,
    padding: space.md,
  },
  scorePill: {
    width: 52,
    height: 44,
    borderRadius: radius.sm,
    ...curve,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
