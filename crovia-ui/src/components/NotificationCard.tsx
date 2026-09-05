import React, { useState } from 'react';
import { LayoutAnimation, Platform, UIManager } from 'react-native';
import { Box, Text, VStack, HStack, Pressable, Center } from '@gluestack-ui/themed';
import { MotionButton } from './MotionButton';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

export type NotificationCategory =
  | 'crowd'
  | 'haven'
  | 'network'
  | 'reroute'
  | 'reward';

export type Notification = {
  id: string;
  category: NotificationCategory;
  title: string;
  summary: string;
  detail: string;
  action: string;
  time: string;
  unread?: boolean;
};

// Hardcoded theme colors
const cardBg = '#1E2336';
const textPrimary = '#F0F0F0';
const textMuted = '#9CA3AF';
const borderColor = '#2A314A';
const accentColor = '#F2A93B';

export function useCategoryStyle() {
  return {
    crowd: { fg: '#ff4444', bg: 'rgba(255, 68, 68, 0.15)', glyph: '!', name: 'Crowd warning' },
    haven: { fg: '#00C851', bg: 'rgba(0, 200, 81, 0.15)', glyph: 'H', name: 'Safe haven' },
    network: { fg: '#33b5e5', bg: 'rgba(51, 181, 229, 0.15)', glyph: '~', name: 'Network update' },
    reroute: { fg: accentColor, bg: 'rgba(242, 169, 59, 0.15)', glyph: '>', name: 'Reroute' },
    reward: { fg: '#FFBB33', bg: 'rgba(255, 187, 51, 0.15)', glyph: '*', name: 'Reward' },
  } as Record<NotificationCategory, { fg: string; bg: string; glyph: string; name: string }>;
}

export function NotificationCard({
  item,
  onAction,
}: {
  item: Notification;
  onAction?: (n: Notification) => void;
}) {
  const cat = useCategoryStyle()[item.category];
  const [open, setOpen] = useState(false);

  const toggle = () => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setOpen((o) => !o);
  };

  return (
    <Pressable
      onPress={toggle}
      accessibilityRole="button"
      accessibilityState={{ expanded: open }}
    >
      <VStack
        bg={cardBg}
        borderRadius="$xl"
        borderWidth={1}
        borderLeftWidth={item.unread ? 4 : 1}
        borderColor={item.unread ? cat.fg : borderColor}
        p="$4"
        space="md"
        shadowColor="#000"
        shadowOffset={{ width: 0, height: 5 }}
        shadowOpacity={0.2}
        shadowRadius={10}
        elevation={5}
      >
        <HStack space="md" alignItems="flex-start">
          <Center w={40} h={40} borderRadius="$lg" bg={cat.bg}>
            <Text size="lg" fontWeight="$bold" color={cat.fg}>{cat.glyph}</Text>
          </Center>

          <VStack flex={1} space="xs">
            <HStack justifyContent="space-between" alignItems="flex-start">
              <Text size="md" fontWeight="$bold" color={textPrimary} flex={1} numberOfLines={2}>
                {item.title}
              </Text>
              <Text size="xs" color={textMuted} ml="$2">{item.time}</Text>
            </HStack>
            <Text
              size="sm"
              color={textMuted}
              numberOfLines={open ? undefined : 1}
            >
              {item.summary}
            </Text>
          </VStack>
        </HStack>

        {open ? (
          <VStack space="md" mt="$2">
            <Box h={1} bg={borderColor} />
            <Text size="sm" color={textPrimary} lineHeight="$md">{item.detail}</Text>
            
            <HStack justifyContent="flex-end">
              <MotionButton 
                label={item.action}
                color={cat.fg}
                textColor="#161A28"
                onPress={() => onAction?.(item)}
              />
            </HStack>
          </VStack>
        ) : null}
      </VStack>
    </Pressable>
  );
}

export function Toast({
  item,
  onDismiss,
}: {
  item: Notification;
  onDismiss?: () => void;
}) {
  const cat = useCategoryStyle()[item.category];
  return (
    <HStack
      bg={cardBg}
      borderRadius="$xl"
      borderWidth={1}
      borderColor={cat.fg}
      overflow="hidden"
      shadowColor="#000"
      shadowOffset={{ width: 0, height: 10 }}
      shadowOpacity={0.4}
      shadowRadius={15}
      elevation={15}
      alignItems="center"
      pr="$4"
    >
      <Box w={6} alignSelf="stretch" bg={cat.fg} />
      <VStack flex={1} py="$3" px="$3" space="xs">
        <Text size="sm" fontWeight="$bold" color={textPrimary} numberOfLines={1}>
          {item.title}
        </Text>
        <Text size="xs" color={textMuted} numberOfLines={2}>
          {item.summary}
        </Text>
      </VStack>
      <Pressable onPress={onDismiss} hitSlop={10} accessibilityRole="button">
        <Center w={30} h={30} borderRadius="$full" bg={borderColor}>
          <Text size="md" color={textMuted}>×</Text>
        </Center>
      </Pressable>
    </HStack>
  );
}
