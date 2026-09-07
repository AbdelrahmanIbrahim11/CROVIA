import React, { useState } from 'react';
import { ScrollView, Switch } from 'react-native';
import {
  Box,
  Text,
  VStack,
  HStack,
  Pressable,
  Center,
  Input,
  InputField as GluestackInputField,
} from '@gluestack-ui/themed';
import { AppHeader, Sheet } from '../components/Chrome';
import { CityMap } from '../components/CityMap';
import { MarkerData } from '../components/MapMarker';
import { Toast } from '../components/NotificationCard';
import { StatusChip } from '../components/StatusChip';
import { MotionButton } from '../components/MotionButton';
import { blobs, clusters, markers, notifications, REGION, REGION_SUB } from '../data';

const bgColor = '#161A28';
const accentColor = '#F2A93B';
const cardBg = '#1E2336';
const textPrimary = '#F0F0F0';
const textMuted = '#9CA3AF';
const borderColor = '#2A314A';

export function UserDashboardScreen({
  unread,
  onOpenAlerts,
  onSignOut,
}: {
  unread: number;
  onOpenAlerts: () => void;
  onSignOut: () => void;
}) {
  const [selected, setSelected] = useState<MarkerData | null>(null);
  const [zoneOpen, setZoneOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [toastVisible, setToastVisible] = useState(true);

  return (
    <VStack flex={1} bg={bgColor}>
      <AppHeader
        region={REGION}
        subtitle={REGION_SUB}
        unread={unread}
        onBell={onOpenAlerts}
        onSettings={() => setSettingsOpen(true)}
      />

      <Box flex={1}>
        <CityMap
          markers={markers}
          blobs={blobs}
          clusters={clusters}
          activeMarkerId={selected?.id}
          onMarkerPress={setSelected}
        >
          {/* Live alert banner floats over the map */}
          {toastVisible ? (
            <Box position="absolute" top="$4" left="$4" right="$4">
              <Toast item={notifications[0]} onDismiss={() => setToastVisible(false)} />
            </Box>
          ) : null}

          {/* Legend */}
          <VStack
            position="absolute"
            left="$4"
            bottom={200}
            bg="rgba(30, 35, 54, 0.9)"
            borderWidth={1}
            borderColor={borderColor}
            borderRadius="$lg"
            p="$3"
            space="sm"
          >
            {[
              { c: '#00C851', l: 'Calm' },
              { c: '#33b5e5', l: 'Watch' },
              { c: accentColor, l: 'Elevated' },
              { c: '#ff4444', l: 'Critical' },
            ].map((row) => (
              <HStack key={row.l} alignItems="center" space="xs">
                <Box w={10} h={10} borderRadius="$full" bg={row.c} />
                <Text size="xs" color={textMuted} fontWeight="$medium">{row.l}</Text>
              </HStack>
            ))}
          </VStack>

          {/* Zone lookup trigger */}
          <Pressable
            onPress={() => setZoneOpen(true)}
            accessibilityRole="button"
            position="absolute"
            right="$4"
            bottom={200}
          >
            <Center w={48} h={48} bg="rgba(30, 35, 54, 0.9)" borderWidth={1} borderColor={borderColor} borderRadius="$lg">
              <Text size="2xl" color={accentColor}>◎</Text>
            </Center>
          </Pressable>
        </CityMap>

        {/* Standing status card */}
        <VStack
          position="absolute"
          left="$4"
          right="$4"
          bottom="$4"
          bg={cardBg}
          borderWidth={1}
          borderColor={borderColor}
          borderRadius="$xl"
          p="$5"
          space="lg"
          shadowColor="#000"
          shadowOffset={{ width: 0, height: 10 }}
          shadowOpacity={0.3}
          shadowRadius={15}
          elevation={10}
        >
          <HStack alignItems="flex-start" justifyContent="space-between">
            <VStack space="xs" flex={1} mr="$2">
              <Text size="lg" fontWeight="$bold" color={textPrimary}>Your area right now</Text>
              <Text size="sm" color={textMuted}>Crowd building 180 m north of you</Text>
            </VStack>
            <StatusChip level="critical" />
          </HStack>
          <MotionButton 
            label="Show me the way out"
            color={accentColor}
            textColor="#161A28"
            onPress={() => setSelected(markers[1])}
          />
        </VStack>
      </Box>

      {/* Marker detail */}
      <Sheet
        visible={!!selected}
        title={selected?.name ?? ''}
        onClose={() => setSelected(null)}
      >
        <Text size="md" color={textMuted} lineHeight="$md">{selected?.detail}</Text>
        <Text size="sm" color={accentColor} fontWeight="$bold">{selected?.distance} from you</Text>
        
        <HStack space="md" mt="$4">
          <MotionButton 
            label="Get directions"
            color={accentColor}
            textColor="#161A28"
            flex={1}
            onPress={() => setSelected(null)}
          />
          <MotionButton 
            label="Close"
            variant="outline"
            color={borderColor}
            textColor={textPrimary}
            flex={1}
            onPress={() => setSelected(null)}
          />
        </HStack>
      </Sheet>

      {/* Zone lookup */}
      <Sheet visible={zoneOpen} title="Check a specific spot" onClose={() => setZoneOpen(false)}>
        <Text size="sm" color={textMuted}>
          Enter a point and a radius to see crowd conditions there before you travel.
        </Text>
        <HStack space="md">
          <VStack space="xs" flex={1}>
            <Text size="xs" color={textPrimary} fontWeight="$bold">Latitude</Text>
            <Input variant="outline" size="xl" borderRadius="$lg" borderColor={borderColor} $focus-borderColor={accentColor}>
              <GluestackInputField placeholder="31.2404" keyboardType="numeric" color={textPrimary} placeholderTextColor="#6B7280" />
            </Input>
          </VStack>
          <VStack space="xs" flex={1}>
            <Text size="xs" color={textPrimary} fontWeight="$bold">Longitude</Text>
            <Input variant="outline" size="xl" borderRadius="$lg" borderColor={borderColor} $focus-borderColor={accentColor}>
              <GluestackInputField placeholder="29.9553" keyboardType="numeric" color={textPrimary} placeholderTextColor="#6B7280" />
            </Input>
          </VStack>
        </HStack>
        <VStack space="xs">
          <Text size="xs" color={textPrimary} fontWeight="$bold">Radius in metres</Text>
          <Input variant="outline" size="xl" borderRadius="$lg" borderColor={borderColor} $focus-borderColor={accentColor}>
            <GluestackInputField placeholder="500" keyboardType="numeric" color={textPrimary} placeholderTextColor="#6B7280" />
          </Input>
        </VStack>
        
        <HStack space="md" mt="$2">
          <MotionButton 
            label="Check this area"
            color={accentColor}
            textColor="#161A28"
            flex={1}
            onPress={() => setZoneOpen(false)}
          />
          <MotionButton 
            label="Cancel"
            variant="outline"
            color={borderColor}
            textColor={textPrimary}
            flex={1}
            onPress={() => setZoneOpen(false)}
          />
        </HStack>
      </Sheet>

      {/* Settings */}
      <Sheet visible={settingsOpen} title="Settings" onClose={() => setSettingsOpen(false)}>
        <ScrollView style={{ maxHeight: 300 }}>
          <HStack alignItems="center" py="$4" borderBottomWidth={1} borderBottomColor={borderColor}>
            <VStack flex={1} pr="$4">
              <Text size="lg" fontWeight="$bold" color={textPrimary}>Location Services</Text>
              <Text size="xs" color={textMuted}>Required for live crowd warnings near you</Text>
            </VStack>
            <Switch
              value={true}
              trackColor={{ true: accentColor, false: '#4B5563' }}
              thumbColor={textPrimary}
            />
          </HStack>
          <HStack alignItems="center" py="$4" borderBottomWidth={1} borderBottomColor={borderColor}>
            <VStack flex={1} pr="$4">
              <Text size="lg" fontWeight="$bold" color={textPrimary}>Push Notifications</Text>
              <Text size="xs" color={textMuted}>Get alerted instantly</Text>
            </VStack>
            <Switch
              value={true}
              trackColor={{ true: accentColor, false: '#4B5563' }}
              thumbColor={textPrimary}
            />
          </HStack>
        </ScrollView>

        <MotionButton 
          label="Sign out"
          variant="outline"
          color="#ff4444"
          textColor="#ff4444"
          mt="$4"
          onPress={() => {
            setSettingsOpen(false);
            onSignOut();
          }}
        />
      </Sheet>
    </VStack>
  );
}
