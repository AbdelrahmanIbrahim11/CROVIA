import React, { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { Button } from '../components/Button';
import { InputField } from '../components/InputField';
import { useTheme } from '../theme/ThemeProvider';
import { curve, hairline, radius, space, type } from '../theme/tokens';

const profile = {
  name: 'Nour Mahmoud',
  phone: '+20 100 482 9917',
  email: 'nour.mahmoud@example.com',
};

export function ProfileScreen({ onSignOut }: { onSignOut: () => void }) {
  const { colors } = useTheme();
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState(false);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bgBase }}
      contentContainerStyle={styles.scroll}
    >
      <View style={styles.head}>
        <View style={[styles.avatar, { backgroundColor: colors.accentDim, borderColor: colors.accent }]}>
          <Text style={[type.metricMd, { color: colors.accent }]}>NM</Text>
        </View>
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={[type.h2, { color: colors.textPrimary }]}>{profile.name}</Text>
          <Text style={[type.bodySm, { color: colors.textMuted }]}>Citizen account</Text>
        </View>
      </View>

      {saved && !editing ? (
        <View style={[styles.banner, { backgroundColor: colors.safeDim, borderColor: colors.safe }]}>
          <Text style={[type.bodySm, { color: colors.safe }]}>Your details were saved.</Text>
        </View>
      ) : null}

      <View style={styles.section}>
        <Text style={[type.h3, { color: colors.textPrimary }]}>Your details</Text>

        {editing ? (
          <View style={styles.form}>
            <InputField label="Full name" defaultValue={profile.name} />
            <InputField
              label="Phone number"
              defaultValue={profile.phone}
              keyboardType="phone-pad"
              status="success"
              helper="Verified"
            />
            <InputField
              label="Email"
              defaultValue={profile.email}
              keyboardType="email-address"
              autoCapitalize="none"
            />
            <View style={styles.actions}>
              <Button
                label="Save changes"
                onPress={() => {
                  setEditing(false);
                  setSaved(true);
                }}
              />
              <Button label="Cancel" variant="ghost" onPress={() => setEditing(false)} />
            </View>
          </View>
        ) : (
          <View style={[styles.readout, { borderColor: colors.borderSubtle }]}>
            {[
              ['Name', profile.name],
              ['Phone', profile.phone],
              ['Email', profile.email],
            ].map(([label, value], i) => (
              <View
                key={label}
                style={[
                  styles.row,
                  i < 2 && { borderBottomWidth: hairline, borderBottomColor: colors.borderSubtle },
                ]}
              >
                <Text style={[type.label, { color: colors.textMuted, width: 72 }]}>{label}</Text>
                <Text style={[type.body, { color: colors.textPrimary, flex: 1 }]}>{value}</Text>
              </View>
            ))}
          </View>
        )}

        {!editing ? <Button label="Edit details" variant="secondary" onPress={() => setEditing(true)} /> : null}
      </View>

      <View style={styles.section}>
        <Text style={[type.h3, { color: colors.textPrimary }]}>Rewards</Text>
        <View style={[styles.reward, { backgroundColor: colors.rewardDim, borderColor: colors.reward }]}>
          <Text style={[type.metricLg, { color: colors.reward }]}>3 GB</Text>
          <Text style={[type.bodySm, { color: colors.textSecondary }]}>
            Earned this month for following rerouting guidance during crowd events.
          </Text>
        </View>
      </View>

      <Button label="Sign out" variant="secondary" full onPress={onSignOut} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: space.xl, paddingTop: 56, gap: space.xl, paddingBottom: 48 },
  head: { flexDirection: 'row', alignItems: 'center', gap: space.lg },
  avatar: {
    width: 64,
    height: 64,
    borderRadius: radius.lg,
    ...curve,
    borderWidth: hairline,
    alignItems: 'center',
    justifyContent: 'center',
  },
  banner: { borderWidth: hairline, borderRadius: radius.md,
    ...curve, padding: space.md },
  section: { gap: space.md },
  form: { gap: space.lg },
  readout: { borderWidth: hairline, borderRadius: radius.md,
    ...curve, paddingHorizontal: space.lg },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingVertical: 14 },
  actions: { flexDirection: 'row', gap: space.md, alignItems: 'center' },
  reward: { borderWidth: hairline, borderRadius: radius.lg,
    ...curve, padding: space.lg, gap: 6 },
});
