import React, { useCallback, useEffect, useState } from 'react';
import { ScrollView } from 'react-native';
import {
  Box,
  Text,
  VStack,
  HStack,
  Center,
} from '@gluestack-ui/themed';
import { Pressable, Switch } from 'react-native';
import { MotionButton } from '../components/MotionButton';
import { ConsentState, fetchMyConsent, setMyConsent } from '../api';
import { loadSession } from '../session';

const bgColor = '#161A28';
const accentColor = '#F2A93B';
const cardBg = '#1E2336';
const textPrimary = '#F0F0F0';
const textMuted = '#9CA3AF';
const borderColor = '#2A314A';

export function ProfileScreen({ onSignOut }: { onSignOut: () => void }) {

  // The real account, not a made-up one. The name and email come from the token
  // issued at sign-in; the phone number and monitoring state come from the
  // backend, because only it knows whether consent is currently on.
  const session = loadSession();
  const [consent, setConsent] = useState<ConsentState | null>(null);
  const [switching, setSwitching] = useState(false);

  const refreshConsent = useCallback(async () => {
    setConsent(await fetchMyConsent());
  }, []);

  useEffect(() => {
    refreshConsent();
  }, [refreshConsent]);

  async function toggleMonitoring(on: boolean) {
    if (!consent?.phone_number) return;
    setSwitching(true);
    await setMyConsent(consent.phone_number, on);
    await refreshConsent();
    setSwitching(false);
  }

  const profile = {
    name: session?.username ?? 'Signed out',
    phone: consent?.phone_number ?? '—',
    email: session?.email ?? '—',
  };
  const initials = (session?.username ?? '?')
    .split(' ')
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  return (
    <Box flex={1} bg={bgColor}>
      <ScrollView contentContainerStyle={{ padding: 24, paddingTop: 40, paddingBottom: 100 }}>
        <VStack space="2xl">
          <HStack alignItems="center" space="lg">
            <Center w={70} h={70} borderRadius="$2xl" bg="rgba(242, 169, 59, 0.15)" borderWidth={1} borderColor={accentColor}>
              <Text size="2xl" fontWeight="$bold" color={accentColor}>{initials}</Text>
            </Center>
            <VStack space="xs" flex={1}>
              <Text size="2xl" fontWeight="$bold" color={textPrimary}>{profile.name}</Text>
              <Text size="sm" color={textMuted}>Citizen account</Text>
            </VStack>
          </HStack>

          {/*
            The one control a person genuinely needs over this product. It is
            placed above their details rather than buried in settings, because
            being monitored is the thing worth being able to find and stop.
          */}
          <VStack space="lg">
            <Text size="xl" fontWeight="$bold" color={textPrimary}>Crowd warnings</Text>
            <Box bg={cardBg} borderRadius="$xl" borderWidth={1}
              borderColor={consent?.monitored ? accentColor : borderColor} p="$5">
              <HStack alignItems="center" space="lg">
                <VStack flex={1} space="xs">
                  <Text size="md" fontWeight="$bold" color={textPrimary}>
                    {consent?.monitored ? 'CROVIA is watching for you' : 'Not switched on'}
                  </Text>
                  <Text size="xs" color={textMuted} lineHeight="$sm">
                    {consent?.monitored
                      ? 'The network is asked whether your phone is inside a crowded area. Never where you are, only yes or no.'
                      : 'You can use the map, but you will not be warned about a dangerous crowd near you.'}
                  </Text>
                </VStack>
                <Switch
                  value={!!consent?.monitored}
                  disabled={switching || !consent?.phone_number}
                  onValueChange={toggleMonitoring}
                  trackColor={{ true: accentColor, false: '#4B5563' }}
                  thumbColor={textPrimary}
                />
              </HStack>
              {consent?.monitored && consent.granted_at ? (
                <Text size="xs" color={textMuted} mt="$3">
                  On since {new Date(consent.granted_at).toLocaleDateString()}. Switch it
                  off and monitoring stops immediately.
                </Text>
              ) : null}
            </Box>
          </VStack>

          <VStack space="lg">
            <Text size="xl" fontWeight="$bold" color={textPrimary}>Your details</Text>

            <Box bg={cardBg} borderRadius="$xl" borderWidth={1} borderColor={borderColor} px="$5" py="$2">
              {[
                ['Name', profile.name],
                ['Phone', profile.phone],
                ['Email', profile.email],
              ].map(([label, value], i) => (
                <HStack
                  key={label}
                  alignItems="center"
                  py="$4"
                  borderBottomWidth={i < 2 ? 1 : 0}
                  borderBottomColor={borderColor}
                >
                  <Text size="sm" color={textMuted} w={80}>{label}</Text>
                  <Text size="md" color={textPrimary} flex={1}>{value}</Text>
                </HStack>
              ))}
            </Box>
          </VStack>

          <MotionButton 
            label="Sign out"
            variant="outline"
            color="#ff4444"
            textColor="#ff4444"
            mt="$4"
            onPress={onSignOut}
          />
        </VStack>
      </ScrollView>
    </Box>
  );
}
