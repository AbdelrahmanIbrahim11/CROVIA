import React from 'react';
import { Modal, Dimensions, Image as RNImage, Animated, Platform } from 'react-native';
import {
  Box,
  Text,
  VStack,
  HStack,
  Pressable,
  Center,
} from '@gluestack-ui/themed';
import { Badge } from './StatusChip';

const bgColor = '#161A28';
const accentColor = '#F2A93B';
const cardBg = '#1E2336';
const textPrimary = '#F0F0F0';
const textMuted = '#9CA3AF';
const borderColor = '#2A314A';

export function AppHeader({
  region,
  subtitle,
  unread = 0,
  onBell,
  onSettings,
}: {
  region: string;
  subtitle?: string;
  unread?: number;
  onBell?: () => void;
  onSettings?: () => void;
}) {
  return (
    <HStack
      bg={bgColor}
      px="$6"
      py="$4"
      alignItems="center"
      justifyContent="space-between"
      borderBottomWidth={1}
      borderBottomColor={borderColor}
      space="md"
    >
      <RNImage 
        source={require('../../assets/logo.png')} 
        style={{ width: 100, height: 30, resizeMode: 'contain' }} 
      />
      
      <VStack flex={1} ml="$2">
        <Text size="md" fontWeight="$bold" color={textPrimary} numberOfLines={1}>
          {region}
        </Text>
        {subtitle ? (
          <Text size="xs" color={textMuted} numberOfLines={1}>
            {subtitle}
          </Text>
        ) : null}
      </VStack>

      {/* The bell used to live here, duplicating the Alerts tab at the bottom
          which already carries the same unread count. Two places showing one
          number is two places to keep in step, and the tab is the one people
          actually reach for. */}
      <HStack space="md">
        <Pressable onPress={onSettings} hitSlop={10} accessibilityRole="button" accessibilityLabel="Settings">
          <Center w={40} h={40} borderRadius="$full" borderWidth={1} borderColor={borderColor} bg={cardBg}>
            <Text size="lg" color={textPrimary}>⋯</Text>
          </Center>
        </Pressable>
      </HStack>
    </HStack>
  );
}

export function Sheet({
  visible,
  title,
  onClose,
  children,
}: {
  visible: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.6)' }} onPress={onClose} />
      <Box
        position="absolute"
        bottom={0}
        left={0}
        right={0}
        bg={cardBg}
        borderTopLeftRadius="$3xl"
        borderTopRightRadius="$3xl"
        p="$6"
        pb="$10"
        shadowColor="#000"
        shadowOffset={{ width: 0, height: -5 }}
        shadowOpacity={0.3}
        shadowRadius={15}
        elevation={20}
      >
        <Center w={40} h={4} borderRadius="$full" bg={borderColor} alignSelf="center" mt="-$2" mb="$4" />
        <HStack alignItems="center" mb="$4">
          <Text size="xl" fontWeight="$bold" color={textPrimary} flex={1}>{title}</Text>
          <Pressable onPress={onClose} hitSlop={10} accessibilityRole="button">
            <Center w={30} h={30} borderRadius="$full" bg="#2A314A">
              <Text size="lg" color={textMuted}>×</Text>
            </Center>
          </Pressable>
        </HStack>
        <VStack space="lg">
          {children}
        </VStack>
      </Box>
    </Modal>
  );
}

export type TabKey = 'map' | 'alerts' | 'profile';

function MotionTab({ 
  item, 
  active, 
  unread = 0, 
  onPress 
}: { 
  item: { key: TabKey; label: string; glyph: string }; 
  active: boolean; 
  unread?: number; 
  onPress: () => void;
}) {
  const translateY = React.useRef(new Animated.Value(0)).current;
  const scale = React.useRef(new Animated.Value(1)).current;

  const handleHoverIn = () => {
    if (Platform.OS === 'web') {
      Animated.parallel([
        Animated.spring(translateY, { toValue: -4, friction: 5, useNativeDriver: true }),
        Animated.spring(scale, { toValue: 1.05, friction: 5, useNativeDriver: true })
      ]).start();
    }
  };

  const handleHoverOut = () => {
    if (Platform.OS === 'web') {
      Animated.parallel([
        Animated.spring(translateY, { toValue: 0, friction: 5, useNativeDriver: true }),
        Animated.spring(scale, { toValue: 1, friction: 5, useNativeDriver: true })
      ]).start();
    }
  };

  const handlePressIn = () => {
    Animated.spring(scale, { toValue: 0.9, friction: 5, useNativeDriver: true }).start();
  };

  const handlePressOut = () => {
    Animated.spring(scale, { toValue: 1, friction: 5, useNativeDriver: true }).start();
  };

  return (
    <Pressable
      onPress={onPress}
      onPressIn={handlePressIn}
      onPressOut={handlePressOut}
      //@ts-ignore
      onHoverIn={handleHoverIn}
      //@ts-ignore
      onHoverOut={handleHoverOut}
      accessibilityRole="tab"
      accessibilityState={{ selected: active }}
      flex={1}
      alignItems="center"
    >
      <Animated.View style={{ transform: [{ translateY }, { scale }] }}>
        <VStack alignItems="center" space="xs">
          <Box>
            <Text size="xl" color={active ? accentColor : textMuted}>
              {item.glyph}
            </Text>
            {item.key === 'alerts' && unread > 0 ? <Badge count={unread} /> : null}
          </Box>
          <Text size="xs" fontWeight={active ? "$bold" : "$medium"} color={active ? accentColor : textMuted}>
            {item.label}
          </Text>
        </VStack>
      </Animated.View>
    </Pressable>
  );
}

export function TabBar({
  active,
  unread = 0,
  onChange,
}: {
  active: TabKey;
  unread?: number;
  onChange: (k: TabKey) => void;
}) {
  const tabs: { key: TabKey; label: string; glyph: string }[] = [
    { key: 'map', label: 'Map', glyph: '◈' },
    { key: 'alerts', label: 'Alerts', glyph: '◔' },
    { key: 'profile', label: 'Profile', glyph: '◐' },
  ];

  return (
    <HStack
      bg={bgColor}
      pt="$3"
      pb="$6"
      borderTopWidth={1}
      borderTopColor={borderColor}
    >
      {tabs.map((t) => (
        <MotionTab 
          key={t.key} 
          item={t} 
          active={t.key === active} 
          unread={unread} 
          onPress={() => onChange(t.key)} 
        />
      ))}
    </HStack>
  );
}

export function Metric({
  value,
  label,
  tint,
}: {
  value: string;
  label: string;
  tint?: string;
}) {
  return (
    <VStack space="xs" flex={1}>
      <Text size="2xl" fontWeight="$bold" color={tint ?? textPrimary}>{value}</Text>
      <Text size="xs" color={textMuted}>{label}</Text>
    </VStack>
  );
}
