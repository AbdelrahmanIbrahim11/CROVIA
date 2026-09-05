import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';
import { Button } from '../components/Button';
import { AppHeader, Sheet } from '../components/Chrome';
import { CityMap } from '../components/CityMap';
import { InputField } from '../components/InputField';
import { MarkerData } from '../components/MapMarker';
import { Toast } from '../components/NotificationCard';
import { StatusChip } from '../components/StatusChip';
import { blobs, markers, notifications, REGION, REGION_SUB } from '../data';
import { useTheme } from '../theme/ThemeProvider';
import { curve, hairline, radius, space, type } from '../theme/tokens';

export function UserDashboardScreen({
  unread,
  onOpenAlerts,
  onSignOut,
}: {
  unread: number;
  onOpenAlerts: () => void;
  onSignOut: () => void;
}) {
  const { colors, scheme, toggleScheme } = useTheme();
  const [selected, setSelected] = useState<MarkerData | null>(null);
  const [zoneOpen, setZoneOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [toastVisible, setToastVisible] = useState(true);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bgBase }}>
      <AppHeader
        region={REGION}
        subtitle={REGION_SUB}
        unread={unread}
        onBell={onOpenAlerts}
        onSettings={() => setSettingsOpen(true)}
      />

      <View style={{ flex: 1 }}>
        <CityMap
          markers={markers}
          blobs={blobs}
          activeMarkerId={selected?.id}
          onMarkerPress={setSelected}
        >
          {/* Live alert banner floats over the map */}
          {toastVisible ? (
            <View style={styles.toastSlot}>
              <Toast item={notifications[0]} onDismiss={() => setToastVisible(false)} />
            </View>
          ) : null}

          {/* Legend */}
          <View style={[styles.legend, { backgroundColor: colors.bgSurface, borderColor: colors.borderSubtle }]}>
            {[
              { c: colors.density1, l: 'Calm' },
              { c: colors.density2, l: 'Watch' },
              { c: colors.density3, l: 'Elevated' },
              { c: colors.density4, l: 'Critical' },
            ].map((row) => (
              <View key={row.l} style={styles.legendRow}>
                <View style={[styles.legendDot, { backgroundColor: row.c }]} />
                <Text style={[type.caption, { color: colors.textSecondary }]}>{row.l}</Text>
              </View>
            ))}
          </View>

          {/* Zone lookup trigger */}
          <Pressable
            onPress={() => setZoneOpen(true)}
            accessibilityRole="button"
            style={[styles.fab, { backgroundColor: colors.bgSurface, borderColor: colors.borderSubtle }]}
          >
            <Text style={{ fontSize: 18, color: colors.accent }}>◎</Text>
          </Pressable>
        </CityMap>

        {/* Standing status card */}
        <View
          style={[
            styles.statusCard,
            { backgroundColor: colors.bgSurface, borderColor: colors.borderSubtle },
          ]}
        >
          <View style={styles.statusTop}>
            <View style={{ flex: 1, gap: 4 }}>
              <Text style={[type.h3, { color: colors.textPrimary }]}>Your area right now</Text>
              <Text style={[type.bodySm, { color: colors.textSecondary }]}>
                Crowd building 180 m north of you
              </Text>
            </View>
            <StatusChip level="critical" />
          </View>
          <Button label="Show me the way out" full onPress={() => setSelected(markers[1])} />
        </View>
      </View>

      {/* Marker detail */}
      <Sheet
        visible={!!selected}
        title={selected?.name ?? ''}
        onClose={() => setSelected(null)}
      >
        <Text style={[type.body, { color: colors.textSecondary }]}>{selected?.detail}</Text>
        <View style={styles.metaRow}>
          <Text style={[type.label, { color: colors.textMuted }]}>
            {selected?.distance} from you
          </Text>
        </View>
        <View style={styles.sheetActions}>
          <Button label="Get directions" onPress={() => setSelected(null)} />
          <Button label="Close" variant="ghost" onPress={() => setSelected(null)} />
        </View>
      </Sheet>

      {/* Zone lookup */}
      <Sheet visible={zoneOpen} title="Check a specific spot" onClose={() => setZoneOpen(false)}>
        <Text style={[type.bodySm, { color: colors.textSecondary }]}>
          Enter a point and a radius to see crowd conditions there before you travel.
        </Text>
        <View style={styles.pairRow}>
          <View style={{ flex: 1 }}>
            <InputField label="Latitude" placeholder="31.2404" keyboardType="numeric" />
          </View>
          <View style={{ flex: 1 }}>
            <InputField label="Longitude" placeholder="29.9553" keyboardType="numeric" />
          </View>
        </View>
        <InputField label="Radius in metres" placeholder="500" keyboardType="numeric" />
        <View style={styles.sheetActions}>
          <Button label="Check this area" onPress={() => setZoneOpen(false)} />
          <Button label="Cancel" variant="ghost" onPress={() => setZoneOpen(false)} />
        </View>
      </Sheet>

      {/* Settings */}
      <Sheet visible={settingsOpen} title="Settings" onClose={() => setSettingsOpen(false)}>
        <ScrollView style={{ maxHeight: 300 }}>
          <View style={[styles.settingRow, { borderColor: colors.borderSubtle }]}>
            <View style={{ flex: 1 }}>
              <Text style={[type.h4, { color: colors.textPrimary }]}>Daylight theme</Text>
              <Text style={[type.caption, { color: colors.textMuted }]}>
                Easier to read outdoors in bright sun
              </Text>
            </View>
            <Switch
              value={scheme === 'light'}
              onValueChange={toggleScheme}
              trackColor={{ true: colors.accent, false: colors.borderStrong }}
              thumbColor={colors.bgSurface}
            />
          </View>

          <View style={[styles.settingRow, { borderColor: colors.borderSubtle }]}>
            <View style={{ flex: 1 }}>
              <Text style={[type.h4, { color: colors.textPrimary }]}>Share my location</Text>
              <Text style={[type.caption, { color: colors.textMuted }]}>
                Required for crowd warnings near you
              </Text>
            </View>
            <Switch
              value
              trackColor={{ true: colors.accent, false: colors.borderStrong }}
              thumbColor={colors.bgSurface}
            />
          </View>
        </ScrollView>

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
  toastSlot: { position: 'absolute', top: space.lg, left: space.lg, right: space.lg },
  legend: {
    position: 'absolute',
    left: space.lg,
    bottom: 200,
    borderWidth: hairline,
    borderRadius: radius.md,
    ...curve,
    padding: 10,
    gap: 6,
  },
  legendRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  legendDot: { width: 8, height: 8, borderRadius: 4 },
  fab: {
    position: 'absolute',
    right: space.lg,
    bottom: 200,
    width: 48,
    height: 48,
    borderRadius: radius.md,
    ...curve,
    borderWidth: hairline,
    alignItems: 'center',
    justifyContent: 'center',
  },
  statusCard: {
    position: 'absolute',
    left: space.lg,
    right: space.lg,
    bottom: space.lg,
    borderWidth: hairline,
    borderRadius: radius.lg,
    ...curve,
    padding: space.lg,
    gap: space.lg,
  },
  statusTop: { flexDirection: 'row', alignItems: 'flex-start', gap: space.md },
  metaRow: { flexDirection: 'row' },
  sheetActions: { flexDirection: 'row', gap: space.md, alignItems: 'center' },
  pairRow: { flexDirection: 'row', gap: space.md },
  settingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.lg,
    borderBottomWidth: hairline,
  },
});
