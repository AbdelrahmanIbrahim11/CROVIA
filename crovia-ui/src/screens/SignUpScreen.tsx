import React, { useState } from 'react';
import { KeyboardAvoidingView, Platform, Image as RNImage } from 'react-native';
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
import { register } from '../session';

export function SignUpScreen({
  onCreate,
  onBack,
}: {
  onCreate: () => void;
  onBack: () => void;
}) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [number, setNumber] = useState('');
  const [password, setPassword] = useState('');
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError(null);
    if (!name.trim() || !email.trim() || !number.trim() || !password) {
      setError('Please fill in every field.');
      return;
    }
    if (password.length < 8) {
      setError('Your password needs at least 8 characters.');
      return;
    }
    // Checked here as well as on the server, so a wrong number is answered
    // instantly instead of after a round trip.
    if (!/^\+?[0-9]{5,15}$/.test(number.replace(/\s+/g, ''))) {
      setError('Enter a phone number of 5 to 15 digits, with the country code — for example +974 3000 0000.');
      return;
    }
    setBusy(true);
    const res = await register({
      username: name.trim(),
      email: email.trim(),
      number: number.replace(/\s+/g, ''),
      password,
      userType: 'normal',
      consent,
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.error);
      return;
    }
    onCreate();
  }
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
          {/* Logo Image */}
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
                <DropInText text="Create your citizen account" color={textPrimary} />
                <TypewriterText text="Join the Crovia network to stay safe." color={textMuted} delay={600} />
              </VStack>

              <VStack space="xl">
                <VStack space="xs">
                  <Text size="sm" fontWeight="$medium" color={textPrimary}>Your name</Text>
                  <Input variant="outline" size="xl" borderRadius="$lg" borderColor="#333A54" $focus-borderColor={accentColor}>
                    <GluestackInputField value={name} onChangeText={setName} placeholder="Nour Mahmoud"
                      color={textPrimary} placeholderTextColor="#6B7280" />
                  </Input>
                </VStack>

                <VStack space="xs">
                  <Text size="sm" fontWeight="$medium" color={textPrimary}>Email</Text>
                  <Input variant="outline" size="xl" borderRadius="$lg" borderColor="#333A54" $focus-borderColor={accentColor}>
                    <GluestackInputField value={email} onChangeText={setEmail} placeholder="you@example.com"
                      keyboardType="email-address" autoCapitalize="none"
                      color={textPrimary} placeholderTextColor="#6B7280" />
                  </Input>
                </VStack>

                <VStack space="xs">
                  <Text size="sm" fontWeight="$medium" color={textPrimary}>Phone number</Text>
                  <Input variant="outline" size="xl" borderRadius="$lg" borderColor="#333A54" $focus-borderColor={accentColor}>
                    <GluestackInputField value={number} onChangeText={setNumber} placeholder="+974 3000 0000"
                      keyboardType="phone-pad" color={textPrimary} placeholderTextColor="#6B7280" />
                  </Input>
                  <Text size="xs" color={textMuted}>
                    Include the country code, for example +974 3000 0000. This is the
                    number CROVIA warns. It is stored as a one-way code, never as a number.
                  </Text>
                </VStack>

                <VStack space="xs">
                  <Text size="sm" fontWeight="$medium" color={textPrimary}>Password</Text>
                  <Input variant="outline" size="xl" borderRadius="$lg" borderColor="#333A54" $focus-borderColor={accentColor}>
                    <GluestackInputField value={password} onChangeText={setPassword} placeholder="At least 8 characters"
                      secureTextEntry onSubmitEditing={submit}
                      color={textPrimary} placeholderTextColor="#6B7280" />
                  </Input>
                </VStack>

                {/*
                  Asked here, in words, at the moment the account is made.
                  Unticked to begin with: an account created without an explicit
                  yes is an account CROVIA does not watch.
                */}
                <Pressable onPress={() => setConsent((c) => !c)} accessibilityRole="checkbox"
                  accessibilityState={{ checked: consent }}>
                  <HStack space="md" alignItems="flex-start"
                    bg={consent ? 'rgba(242, 169, 59, 0.10)' : 'transparent'}
                    borderWidth={1} borderColor={consent ? accentColor : '#333A54'}
                    borderRadius="$lg" p="$3">
                    <Center w={22} h={22} borderRadius="$sm" borderWidth={2}
                      borderColor={consent ? accentColor : '#6B7280'}
                      bg={consent ? accentColor : 'transparent'} mt="$1">
                      {consent ? (
                        <Text size="xs" fontWeight="$bold" color="#161A28">✓</Text>
                      ) : null}
                    </Center>
                    <VStack flex={1} space="xs">
                      <Text size="sm" fontWeight="$bold" color={textPrimary}>
                        Warn me about dangerous crowds near me
                      </Text>
                      <Text size="xs" color={textMuted} lineHeight="$sm">
                        CROVIA asks the mobile network whether your phone is inside a
                        crowded area. It never asks where you are, only yes or no, and it
                        never turns on your GPS. You can switch this off at any time and
                        it stops immediately.
                      </Text>
                      <Text size="xs" color={textMuted}>
                        Leave it unticked and you can still use the map. You just will not
                        be warned.
                      </Text>
                    </VStack>
                  </HStack>
                </Pressable>

                {error ? (
                  <Box bg="rgba(255, 68, 68, 0.12)" borderWidth={1} borderColor="#ff4444" borderRadius="$lg" p="$3">
                    <Text size="sm" color="#ff4444">{error}</Text>
                  </Box>
                ) : null}

                <MotionButton
                  label={busy ? 'Creating…' : 'Create account'}
                  color={accentColor}
                  textColor="#161A28"
                  mt="$2"
                  onPress={submit}
                />
              </VStack>

              <HStack space="sm" justifyContent="center" alignItems="center" mt="$2">
                <Text size="sm" color={textMuted}>
                  Already have an account?
                </Text>
                <Pressable onPress={onBack}>
                  <Text size="sm" color={accentColor} fontWeight="$bold">
                    Sign in
                  </Text>
                </Pressable>
              </HStack>
            </VStack>
          </Box>
        </Center>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
