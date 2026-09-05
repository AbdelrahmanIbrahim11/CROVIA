import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Button } from '../components/Button';
import { Sheet } from '../components/Chrome';
import { StatusChip } from '../components/StatusChip';
import { zoneRows } from '../data';
import { useTheme } from '../theme/ThemeProvider';
import { curve, hairline, radius, space, type } from '../theme/tokens';
import { AdminDashboardScreen } from './AdminDashboardScreen';

const templates = [
  'Move away from the Corniche and head south on El Gaish Road.',
  'This area is at capacity. Use the San Stefano exit.',
  'Emergency vehicles are entering. Clear the roadway.',
];

export function PoliceDashboardScreen({ onSignOut }: { onSignOut: () => void }) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  const [zone, setZone] = useState(zoneRows[0].id);
  const [message, setMessage] = useState('');
  const [sent, setSent] = useState(false);

  const selected = zoneRows.find((z) => z.id === zone)!;

  return (
    <>
      <AdminDashboardScreen
        onSignOut={onSignOut}
        roleLabel="Authority"
        extraToolbar={
          <Pressable
            onPress={() => setOpen(true)}
            accessibilityRole="button"
            accessibilityLabel="Broadcast a message"
            style={[styles.broadcastBtn, { backgroundColor: colors.accent }]}
          >
            <Text style={{ fontSize: 17, color: colors.textOnAccent }}>◈</Text>
          </Pressable>
        }
      />

      <Sheet visible={open} title="Broadcast to a zone" onClose={() => setOpen(false)}>
        <Text style={[type.bodySm, { color: colors.textSecondary }]}>
          Everyone inside the selected zone receives this as a push notification, and by SMS if the
          network there is congested.
        </Text>

        <View style={{ gap: space.sm }}>
          <Text style={[type.label, { color: colors.textSecondary }]}>Zone</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
            {zoneRows.map((z) => {
              const on = z.id === zone;
              return (
                <Pressable
                  key={z.id}
                  onPress={() => setZone(z.id)}
                  accessibilityRole="button"
                  accessibilityState={{ selected: on }}
                  style={[
                    styles.zoneChip,
                    {
                      borderColor: on ? colors.accent : colors.borderSubtle,
                      backgroundColor: on ? colors.accentDim : 'transparent',
                    },
                  ]}
                >
                  <Text style={[type.label, { color: on ? colors.textPrimary : colors.textMuted }]}>
                    {z.name.split(' — ')[0]}
                  </Text>
                </Pressable>
              );
            })}
          </ScrollView>
        </View>

        <View style={[styles.reach, { backgroundColor: colors.bgInset, borderColor: colors.borderSubtle }]}>
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={[type.metricMd, { color: colors.textPrimary }]}>{selected.heads}</Text>
            <Text style={[type.caption, { color: colors.textMuted }]}>people will receive this</Text>
          </View>
          <StatusChip level={selected.level} />
        </View>

        <View style={{ gap: space.sm }}>
          <Text style={[type.label, { color: colors.textSecondary }]}>Message</Text>
          <TextInput
            multiline
            value={message}
            onChangeText={setMessage}
            placeholder="Say what people should do, in one sentence."
            placeholderTextColor={colors.textMuted}
            style={[
              type.body,
              styles.textarea,
              {
                backgroundColor: colors.bgInset,
                borderColor: colors.borderSubtle,
                color: colors.textPrimary,
              },
            ]}
          />
          <View style={styles.templates}>
            {templates.map((t) => (
              <Pressable
                key={t}
                onPress={() => setMessage(t)}
                accessibilityRole="button"
                style={[styles.template, { borderColor: colors.borderSubtle }]}
              >
                <Text style={[type.caption, { color: colors.textSecondary }]} numberOfLines={1}>
                  {t}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>

        {sent ? (
          <View style={[styles.sentBanner, { backgroundColor: colors.safeDim, borderColor: colors.safe }]}>
            <Text style={[type.bodySm, { color: colors.safe }]}>
              Broadcast sent to {selected.heads} people in {selected.name.split(' — ')[0]}.
            </Text>
          </View>
        ) : null}

        <View style={styles.actions}>
          <Button
            label="Send broadcast"
            variant="danger"
            onPress={() => setSent(true)}
            disabled={message.trim().length === 0}
          />
          <Button
            label="Close"
            variant="ghost"
            onPress={() => {
              setOpen(false);
              setSent(false);
            }}
          />
        </View>
      </Sheet>
    </>
  );
}

const styles = StyleSheet.create({
  broadcastBtn: {
    width: 42,
    height: 42,
    borderRadius: radius.sm,
    ...curve,
    alignItems: 'center',
    justifyContent: 'center',
  },
  zoneChip: { paddingHorizontal: 14, paddingVertical: 9, borderRadius: radius.pill,
    ...curve, borderWidth: 1 },
  reach: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    borderWidth: hairline,
    borderRadius: radius.md,
    ...curve,
    padding: space.lg,
  },
  textarea: {
    borderWidth: hairline,
    borderRadius: radius.md,
    ...curve,
    padding: 14,
    minHeight: 96,
    textAlignVertical: 'top',
  },
  templates: { gap: 6 },
  template: { borderWidth: hairline, borderRadius: radius.sm,
    ...curve, paddingHorizontal: 10, paddingVertical: 8 },
  sentBanner: { borderWidth: hairline, borderRadius: radius.md,
    ...curve, padding: space.md },
  actions: { flexDirection: 'row', gap: space.md, alignItems: 'center' },
});
