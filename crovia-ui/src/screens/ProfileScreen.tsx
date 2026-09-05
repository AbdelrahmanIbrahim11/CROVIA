import React, { useState } from 'react';
import { ScrollView } from 'react-native';
import {
  Box,
  Text,
  VStack,
  HStack,
  Center,
  Input,
  InputField as GluestackInputField,
} from '@gluestack-ui/themed';
import { MotionButton } from '../components/MotionButton';

const bgColor = '#161A28';
const accentColor = '#F2A93B';
const cardBg = '#1E2336';
const textPrimary = '#F0F0F0';
const textMuted = '#9CA3AF';
const borderColor = '#2A314A';

const profile = {
  name: 'Nour Mahmoud',
  phone: '+20 100 482 9917',
  email: 'nour.mahmoud@example.com',
};

export function ProfileScreen({ onSignOut }: { onSignOut: () => void }) {
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState(false);

  return (
    <Box flex={1} bg={bgColor}>
      <ScrollView contentContainerStyle={{ padding: 24, paddingTop: 40, paddingBottom: 100 }}>
        <VStack space="2xl">
          <HStack alignItems="center" space="lg">
            <Center w={70} h={70} borderRadius="$2xl" bg="rgba(242, 169, 59, 0.15)" borderWidth={1} borderColor={accentColor}>
              <Text size="2xl" fontWeight="$bold" color={accentColor}>NM</Text>
            </Center>
            <VStack space="xs" flex={1}>
              <Text size="2xl" fontWeight="$bold" color={textPrimary}>{profile.name}</Text>
              <Text size="sm" color={textMuted}>Citizen account</Text>
            </VStack>
          </HStack>

          {saved && !editing ? (
            <Box bg="rgba(0, 200, 81, 0.15)" borderColor="#00C851" borderWidth={1} borderRadius="$lg" p="$4">
              <Text size="sm" color="#00C851" fontWeight="$bold">Your details were saved.</Text>
            </Box>
          ) : null}

          <VStack space="lg">
            <Text size="xl" fontWeight="$bold" color={textPrimary}>Your details</Text>

            {editing ? (
              <VStack space="lg">
                <VStack space="xs">
                  <Text size="sm" fontWeight="$bold" color={textPrimary}>Full name</Text>
                  <Input variant="outline" size="xl" borderRadius="$lg" borderColor={borderColor} $focus-borderColor={accentColor}>
                    <GluestackInputField defaultValue={profile.name} color={textPrimary} />
                  </Input>
                </VStack>
                <VStack space="xs">
                  <Text size="sm" fontWeight="$bold" color={textPrimary}>Phone number</Text>
                  <Input variant="outline" size="xl" borderRadius="$lg" borderColor={borderColor} $focus-borderColor={accentColor}>
                    <GluestackInputField defaultValue={profile.phone} keyboardType="phone-pad" color={textPrimary} />
                  </Input>
                  <Text size="xs" color="#00C851">Verified</Text>
                </VStack>
                <VStack space="xs">
                  <Text size="sm" fontWeight="$bold" color={textPrimary}>Email</Text>
                  <Input variant="outline" size="xl" borderRadius="$lg" borderColor={borderColor} $focus-borderColor={accentColor}>
                    <GluestackInputField defaultValue={profile.email} keyboardType="email-address" autoCapitalize="none" color={textPrimary} />
                  </Input>
                </VStack>
                <HStack space="md" mt="$2">
                  <MotionButton 
                    label="Save changes"
                    color={accentColor}
                    textColor="#161A28"
                    flex={1}
                    onPress={() => { setEditing(false); setSaved(true); }}
                  />
                  <MotionButton 
                    label="Cancel"
                    variant="outline"
                    color={borderColor}
                    textColor={textPrimary}
                    flex={1}
                    onPress={() => setEditing(false)}
                  />
                </HStack>
              </VStack>
            ) : (
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
            )}

            {!editing ? (
              <MotionButton 
                label="Edit details"
                variant="outline"
                color={borderColor}
                textColor={textPrimary}
                onPress={() => setEditing(true)}
              />
            ) : null}
          </VStack>

          <VStack space="md">
            <Text size="xl" fontWeight="$bold" color={textPrimary}>Rewards</Text>
            <VStack bg="rgba(255, 187, 51, 0.15)" borderColor="#FFBB33" borderWidth={1} borderRadius="$xl" p="$5" space="xs">
              <Text size="3xl" fontWeight="$bold" color="#FFBB33">3 GB</Text>
              <Text size="sm" color={textPrimary} lineHeight="$md">
                Earned this month for following rerouting guidance during crowd events.
              </Text>
            </VStack>
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
