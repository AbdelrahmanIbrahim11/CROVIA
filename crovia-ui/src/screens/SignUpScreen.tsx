import React from 'react';
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
import { LogoMark } from '../components/Logo';
import { useTheme } from '../theme/ThemeProvider';
import { curve, hairline, radius, space, type } from '../theme/tokens';

export function SignUpScreen({
  onCreate,
  onBack,
}: {
  onCreate: () => void;
  onBack: () => void;
}) {
  const { colors } = useTheme();

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.bgBase }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        <Pressable onPress={onBack} hitSlop={10} accessibilityRole="button" style={styles.back}>
          <Text style={[type.label, { color: colors.textSecondary }]}>‹ Back</Text>
        </Pressable>

        <LogoMark size={48} />

        <View style={styles.intro}>
          <Text style={[type.displayMd, { color: colors.textPrimary }]}>Create your account</Text>
          <Text style={[type.body, { color: colors.textSecondary }]}>
            Your number is how we reach you when a crowd forms nearby, including by SMS if the
            network is congested.
          </Text>
        </View>

        <View style={styles.form}>
          <InputField label="Full name" placeholder="Nour Mahmoud" autoCapitalize="words" />
          <InputField
            label="Phone number"
            placeholder="+20 100 000 0000"
            keyboardType="phone-pad"
            status="success"
            helper="We'll send a code to confirm this number"
          />
          <InputField
            label="Email"
            placeholder="you@example.com"
            keyboardType="email-address"
            autoCapitalize="none"
          />
          <InputField
            label="Password"
            placeholder="At least 8 characters"
            secureTextEntry
            status="error"
            helper="Use at least 8 characters"
          />
        </View>

        <View style={[styles.consent, { borderColor: colors.borderSubtle }]}>
          <View style={[styles.checkbox, { borderColor: colors.accent, backgroundColor: colors.accent }]}>
            <Text style={{ color: colors.textOnAccent, fontSize: 12, fontWeight: '700' }}>✓</Text>
          </View>
          <Text style={[type.bodySm, { color: colors.textSecondary, flex: 1 }]}>
            Share my approximate location with Crovia so it can warn me about crowds. You can turn
            this off at any time.
          </Text>
        </View>

        <Button label="Create account" full onPress={onCreate} />

        <Text style={[type.caption, { color: colors.textMuted, textAlign: 'center' }]}>
          Location is sampled through your mobile operator, never from a third-party tracker.
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  scroll: { padding: space.xl, paddingTop: 60, gap: space.xl, flexGrow: 1 },
  back: { alignSelf: 'flex-start' },
  intro: { gap: space.md, maxWidth: 460 },
  form: { gap: space.lg },
  consent: {
    flexDirection: 'row',
    gap: space.md,
    borderWidth: hairline,
    borderRadius: radius.md,
    ...curve,
    padding: space.lg,
    alignItems: 'flex-start',
  },
  checkbox: {
    width: 20,
    height: 20,
    borderRadius: 6,
    borderWidth: hairline,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
