import React, { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Button } from '../components/Button';
import { InputField } from '../components/InputField';
import { LogoLockup } from '../components/Logo';
import { useTheme } from '../theme/ThemeProvider';
import { curve, hairline, radius, space, type } from '../theme/tokens';

export type Role = 'citizen' | 'admin' | 'police';

const roles: { key: Role; label: string; blurb: string }[] = [
  { key: 'citizen', label: 'Citizen', blurb: 'Sign in with your phone or email' },
  { key: 'admin', label: 'Admin', blurb: 'Provisioned accounts only' },
  { key: 'police', label: 'Authority', blurb: 'Provisioned accounts only' },
];

export function SignInScreen({
  onSignIn,
  onSignUp,
}: {
  onSignIn: (role: Role) => void;
  onSignUp: () => void;
}) {
  const { colors } = useTheme();
  const [role, setRole] = useState<Role>('citizen');
  const active = roles.find((r) => r.key === role)!;

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.bgBase }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <View style={styles.brand}>
          <LogoLockup size={52} />
        </View>

        <View style={styles.intro}>
          <Text style={[type.displayLg, { color: colors.textPrimary }]}>
            Know where the crowd is
          </Text>
          <Text style={[type.body, { color: colors.textSecondary }]}>
            Live crowd conditions for your city, and a way out before a crush forms.
          </Text>
        </View>

        {/* Role switcher */}
        <View style={[styles.segment, { backgroundColor: colors.bgInset }]}>
          {roles.map((r) => {
            const on = r.key === role;
            return (
              <Pressable
                key={r.key}
                onPress={() => setRole(r.key)}
                accessibilityRole="tab"
                accessibilityState={{ selected: on }}
                style={[
                  styles.segmentItem,
                  on && { backgroundColor: colors.bgElevated, borderColor: colors.accent },
                ]}
              >
                <Text
                  style={[
                    type.label,
                    { color: on ? colors.textPrimary : colors.textMuted },
                  ]}
                >
                  {r.label}
                </Text>
              </Pressable>
            );
          })}
        </View>
        <Text style={[type.caption, { color: colors.textMuted }]}>{active.blurb}</Text>

        <View style={styles.form}>
          {role === 'citizen' ? (
            <InputField
              label="Phone or email"
              placeholder="+20 100 000 0000"
              keyboardType="default"
              autoCapitalize="none"
            />
          ) : (
            <InputField
              label="Work email"
              placeholder="name@alexandria.gov.eg"
              keyboardType="email-address"
              autoCapitalize="none"
            />
          )}

          <InputField label="Password" placeholder="••••••••" secureTextEntry />

          <Pressable accessibilityRole="button" style={styles.forgot}>
            <Text style={[type.label, { color: colors.accent }]}>Forgot password</Text>
          </Pressable>

          <Button label="Sign in" full onPress={() => onSignIn(role)} />
        </View>

        {role === 'citizen' ? (
          <View style={styles.footer}>
            <Text style={[type.bodySm, { color: colors.textMuted }]}>New to Crovia?</Text>
            <Pressable onPress={onSignUp} accessibilityRole="button">
              <Text style={[type.label, { color: colors.accent }]}>Create an account</Text>
            </Pressable>
          </View>
        ) : (
          <View style={[styles.note, { borderColor: colors.borderSubtle }]}>
            <Text style={[type.bodySm, { color: colors.textMuted }]}>
              {active.label} accounts are issued by your operations lead. Contact them if you
              cannot sign in.
            </Text>
          </View>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: space.xl, paddingTop: 72, gap: space.xl, flexGrow: 1 },
  brand: { alignItems: 'flex-start' },
  intro: { gap: space.md, maxWidth: 420 },
  segment: { flexDirection: 'row', padding: 4, borderRadius: radius.md,
    ...curve, gap: 4 },
  segmentItem: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 11,
    borderRadius: radius.sm,
    ...curve,
    borderWidth: hairline,
    borderColor: 'transparent',
  },
  form: { gap: space.lg },
  forgot: { alignSelf: 'flex-end' },
  footer: { flexDirection: 'row', gap: 6, alignItems: 'center', justifyContent: 'center' },
  note: { borderWidth: hairline, borderRadius: radius.md,
    ...curve, padding: space.lg },
});
