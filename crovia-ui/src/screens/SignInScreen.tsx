import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, Image as RNImage, LayoutAnimation, UIManager } from 'react-native';
import {
  Box,
  Text,
  VStack,
  HStack,
  Input,
  InputField as GluestackInputField,
  Pressable,
  ScrollView,
  Center,
} from '@gluestack-ui/themed';
import { MotionButton } from '../components/MotionButton';
import { DropInText, TypewriterText } from '../components/AnimatedText';
import { AnimatedSegmentedControl } from '../components/AnimatedSegmentedControl';
import { Role as AccountRole, Session, signIn as apiSignIn } from '../session';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

export type Role = 'citizen' | 'admin' | 'police';

const roles: { key: Role; label: string; blurb: string }[] = [
  { key: 'citizen', label: 'Citizen', blurb: 'Sign in with your phone or email' },
  { key: 'admin', label: 'Admin', blurb: 'Admin accounts are issued by operations. Contact them if you cannot sign in.' },
  { key: 'police', label: 'Authority', blurb: 'Authority accounts are issued by operations. Contact them if you cannot sign in.' },
];

/** The tab a person picked, translated into the account type the backend knows. */
const ACCOUNT_ROLE: Record<Role, AccountRole> = {
  citizen: 'normal',
  admin: 'admin',
  police: 'authority',
};

export function SignInScreen({
  onSignIn,
  onSignUp,
}: {
  onSignIn: (session: Session) => void;
  onSignUp: () => void;
}) {
  const [role, setRole] = useState<Role>('citizen');
  const active = roles.find((r) => r.key === role)!;

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError(null);
    if (!email.trim() || !password) {
      setError('Enter your email and password.');
      return;
    }
    setBusy(true);
    const res = await apiSignIn(email.trim(), password, ACCOUNT_ROLE[role]);
    setBusy(false);
    if (!res.ok) {
      setError(res.error);
      return;
    }
    onSignIn(res.session);
  }

  const handleRoleChange = (newRole: Role) => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setRole(newRole);
  };

  // Exact colors from the logo
  const bgColor = '#161A28';
  const accentColor = '#F2A93B';
  const cardBg = '#1E2336';
  const textPrimary = '#F0F0F0';
  const textMuted = '#9CA3AF';

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: bgColor }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: 'center' }} keyboardShouldPersistTaps="handled">
        
        <Center px="$6" py="$12">
          {/* Exact Logo Image */}
          <RNImage 
            source={require('../../assets/logo.png')} 
            style={{ width: 300, height: 85, resizeMode: 'contain', marginBottom: 40 }} 
          />

          <Box 
            bg={cardBg} 
            p="$8" 
            borderRadius="$2xl" 
            width="100%" 
            maxWidth={450}
            borderWidth={1}
            borderColor="#2A314A"
            shadowColor="#000"
            shadowOffset={{ width: 0, height: 20 }}
            shadowOpacity={0.4}
            shadowRadius={20}
            elevation={15}
          >
            <VStack space="2xl">
              <VStack space="xs" alignItems="center">
                <DropInText text="Welcome to Crovia" color={textPrimary} />
                <TypewriterText text="Live crowd conditions for your city." color={textMuted} delay={600} />
              </VStack>

              {/* Animated Segmented Control */}
              <AnimatedSegmentedControl
                options={roles}
                value={role}
                onChange={handleRoleChange}
                activeColor={accentColor}
                inactiveColor="#111420"
                textColor={textMuted}
                activeTextColor="#161A28"
              />

              <VStack space="xl">
                <VStack space="xs">
                  <Text size="sm" fontWeight="$medium" color={textPrimary}>
                    {role === 'citizen' ? 'Email' : 'Work email'}
                  </Text>
                  <Input variant="outline" size="xl" borderRadius="$lg" borderColor="#333A54" $focus-borderColor={accentColor}>
                    <GluestackInputField
                      value={email}
                      onChangeText={setEmail}
                      placeholder={role === 'citizen' ? 'you@example.com' : 'name@lusail.qa'}
                      keyboardType="email-address"
                      autoCapitalize="none"
                      color={textPrimary}
                      placeholderTextColor="#6B7280"
                    />
                  </Input>
                </VStack>

                <VStack space="xs">
                  <Text size="sm" fontWeight="$medium" color={textPrimary}>Password</Text>
                  <Input variant="outline" size="xl" borderRadius="$lg" borderColor="#333A54" $focus-borderColor={accentColor}>
                    <GluestackInputField
                      value={password}
                      onChangeText={setPassword}
                      placeholder="••••••••"
                      secureTextEntry
                      onSubmitEditing={submit}
                      color={textPrimary}
                      placeholderTextColor="#6B7280"
                    />
                  </Input>
                </VStack>

                {error ? (
                  <Box bg="rgba(255, 68, 68, 0.12)" borderWidth={1} borderColor="#ff4444" borderRadius="$lg" p="$3">
                    <Text size="sm" color="#ff4444">{error}</Text>
                  </Box>
                ) : null}

                <Pressable alignSelf="flex-end">
                  <Text size="sm" color={accentColor} fontWeight="$bold">
                    Forgot password?
                  </Text>
                </Pressable>

                <MotionButton
                  label={busy ? 'Signing in…' : 'Sign in'}
                  color={accentColor}
                  textColor="#161A28"
                  mt="$2"
                  onPress={submit}
                />
              </VStack>

              {role === 'citizen' ? (
                <HStack space="sm" justifyContent="center" alignItems="center" mt="$2">
                  <Text size="sm" color={textMuted}>
                    Don't have an account?
                  </Text>
                  <Pressable onPress={onSignUp}>
                    <Text size="sm" color={accentColor} fontWeight="$bold">
                      Sign up now
                    </Text>
                  </Pressable>
                </HStack>
              ) : (
                <Box bg="#111420" borderRadius="$lg" p="$4" mt="$2" minHeight={80} justifyContent="center">
                  <TypewriterText text={active.blurb} delay={300} speed={25} size="sm" color={textMuted} textAlign="center" />
                </Box>
              )}
            </VStack>
          </Box>
        </Center>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
