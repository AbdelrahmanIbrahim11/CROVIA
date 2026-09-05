import React from 'react';
import { Pressable, Text } from 'react-native';
import { Center, Box } from '@gluestack-ui/themed';
import { AdminDashboardScreen } from './AdminDashboardScreen';

const accentColor = '#F2A93B';
const textMuted = '#9CA3AF';
const borderColor = '#2A314A';

export function PoliceDashboardScreen({ onSignOut }: { onSignOut: () => void }) {
  return (
    <AdminDashboardScreen
      roleLabel="Authority"
      onSignOut={onSignOut}
      extraToolbar={
        <>
          <Box h={1} bg={borderColor} my="$1" mx="$2" />
          <Pressable accessibilityRole="button">
            <Center w={42} h={42} borderRadius="$md" bg="rgba(255, 68, 68, 0.15)" borderColor="#ff4444" borderWidth={1}>
              <Text style={{ fontSize: 17, color: '#ff4444' }}>!</Text>
            </Center>
          </Pressable>
        </>
      }
    />
  );
}
