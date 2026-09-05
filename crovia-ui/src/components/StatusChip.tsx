import React from 'react';
import { ViewStyle } from 'react-native';
import { Box, Text, HStack, Center } from '@gluestack-ui/themed';

export type Level = 'calm' | 'watch' | 'elevated' | 'critical';

export const levelLabel: Record<Level, string> = {
  calm: 'Calm',
  watch: 'Watch',
  elevated: 'Elevated',
  critical: 'Critical',
};

// Use hardcoded colors matching the new dark theme
const levelColors: Record<Level, { fg: string; bg: string }> = {
  calm: { fg: '#00C851', bg: 'rgba(0, 200, 81, 0.15)' },
  watch: { fg: '#33b5e5', bg: 'rgba(51, 181, 229, 0.15)' },
  elevated: { fg: '#F2A93B', bg: 'rgba(242, 169, 59, 0.15)' },
  critical: { fg: '#ff4444', bg: 'rgba(255, 68, 68, 0.15)' },
};

export function StatusChip({
  level,
  label,
  style,
}: {
  level: Level;
  label?: string;
  style?: ViewStyle;
}) {
  const c = levelColors[level];
  return (
    <HStack
      bg={c.bg}
      px="$3"
      py="$1"
      borderRadius="$full"
      alignItems="center"
      alignSelf="flex-start"
      space="xs"
      style={style}
    >
      <Box w={8} h={8} borderRadius="$full" bg={c.fg} />
      <Text size="xs" fontWeight="$bold" color={c.fg}>
        {label ?? levelLabel[level]}
      </Text>
    </HStack>
  );
}

export function Badge({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <Center
      position="absolute"
      top={-6}
      right={-8}
      minWidth={20}
      h={20}
      borderRadius="$full"
      bg="#ff4444"
      px="$1"
    >
      <Text size="xs" fontWeight="$bold" color="#fff">
        {count > 9 ? '9+' : count}
      </Text>
    </Center>
  );
}
