import React, { useState } from 'react';

import {
  Box,
  Text,
  VStack,
  HStack,
  Pressable,
  Center,

} from '@gluestack-ui/themed';
import { AppHeader, Sheet } from '../components/Chrome';
import { CityMap } from '../components/CityMap';
import { MarkerData } from '../components/MapMarker';
import { Toast } from '../components/NotificationCard';
import { StatusChip } from '../components/StatusChip';
import { MotionButton } from '../components/MotionButton';
import { blobs, markers, REGION, REGION_SUB } from '../data';
import { toOverlays } from '../api';
import { useLiveState } from '../useLiveState';
import { Notification } from '../components/NotificationCard';
import { zoneById } from '../geo';

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
  const { state, connection } = useLiveState(5000);

  const [selected, setSelected] = useState<MarkerData | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [alertOpen, setAlertOpen] = useState(false);
  const [toastVisible, setToastVisible] = useState(true);

  if (connection === 'connecting') {
    return (
      <Center flex={1} bg={bgColor}>
        <Text color={textMuted}>Connecting to CROVIA...</Text>
      </Center>
    );
  }

  const clusters = state ? toOverlays(state).clusters : [];

  // Everything this screen says about safety is derived here, from live state
  // only. It previously read "Crowd building 180 m north of you" with a red
  // badge at all times, including on a completely calm evening — which trains
  // a person to ignore the one time it is true.
  const liveAlert = state?.alerts?.[state.alerts.length - 1] ?? null;
  const live = connection === 'live';

  // The worst zone anywhere in the city, so a person is told something useful
  // even before a zone crosses into a full alarm.
  const worstZone = state
    ? Object.entries(state.zones)
        .filter(([, v]) => v)
        .sort((a, b) => (b[1]!.severity ?? 0) - (a[1]!.severity ?? 0))[0]
    : undefined;

  const level: 'calm' | 'watch' | 'elevated' | 'critical' = !live
    ? 'watch'
    : liveAlert
    ? 'critical'
    : worstZone && worstZone[1]!.severity >= 0.5
    ? 'elevated'
    : worstZone && worstZone[1]!.severity >= 0.2
    ? 'watch'
    : 'calm';

  const headline = !live
    ? 'Cannot reach CROVIA'
    : liveAlert
    ? 'Avoid this area'
    : 'Your area right now';

  // Written so it never claims to know where the person is standing. The
  // network gives a zone, not a doorway, and saying "180 m north of you" would
  // claim a precision that does not exist.
  const detail = !live
    ? 'Showing the map only. Live crowd conditions need the CROVIA service.'
    : liveAlert
    ? `${liveAlert.segment_label} — about ${Math.round(
        liveAlert.people_low,
      ).toLocaleString()}–${Math.round(liveAlert.people_high).toLocaleString()} people, ` +
      `and more are arriving than can get out.`
    : worstZone && worstZone[1]!.severity >= 0.2
    ? `${zoneById[worstZone[0]]?.label ?? 'A crossing'} is getting busy, but people are still moving through.`
    : 'No crowd warnings anywhere in Lusail right now.';

  // The banner appears only when there is a real alarm. When the backend is
  // unreachable it stays hidden rather than falling back to a sample warning:
  // a crowd banner that is not about a crowd is the failure this screen had.
  const toastItem: Notification | null = liveAlert
    ? {
        id: `alert_${liveAlert.zone_id}`,
        category: 'crowd',
        title: liveAlert.segment_label,
        summary: liveAlert.reason,
        detail: liveAlert.reason,
        action: 'Show me the way out',
        time: 'now',
        unread: true,
      }
    : null;



  return (
    <VStack flex={1} bg={bgColor}>
      <AppHeader
        region={REGION}
        subtitle={
          connection === 'live'
            ? liveAlert
              ? `Live · ${liveAlert.segment_label}`
              : 'Live · no crowd warnings'
            : REGION_SUB
        }
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
          {/* Live alert banner floats over the map, and only when one exists */}
          {toastVisible && toastItem ? (
            <Box position="absolute" top="$4" left="$4" right="$4">
              <Toast item={toastItem} onDismiss={() => setToastVisible(false)} />
            </Box>
          ) : null}

          {/* Legend */}
          <VStack
            position="absolute"
            left="$4"
            bottom={260}
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

          {/* Zone lookup trigger removed */}
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
              <Text size="lg" fontWeight="$bold" color={textPrimary}>{headline}</Text>
              <Text size="sm" color={textMuted}>{detail}</Text>
            </VStack>
            <StatusChip level={level} />
          </HStack>
          {liveAlert ? (
            <MotionButton
              label="Show me the way out"
              color={accentColor}
              textColor="#161A28"
              onPress={() => setAlertOpen(true)}
            />
          ) : null}
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

      {/* What to do about the live alarm */}
      <Sheet
        visible={alertOpen && !!liveAlert}
        title={liveAlert?.segment_label ?? ''}
        onClose={() => setAlertOpen(false)}
      >
        <Text size="md" color={textMuted} lineHeight="$md">{liveAlert?.reason}</Text>
        <VStack space="xs" mt="$2">
          <Text size="sm" color={textPrimary} fontWeight="$bold">
            {Math.round(liveAlert?.people_low ?? 0).toLocaleString()}–
            {Math.round(liveAlert?.people_high ?? 0).toLocaleString()} people in this area
          </Text>
          <Text size="xs" color={textMuted}>
            The narrow point is {liveAlert?.width_m ?? 0} m wide and can pass about{' '}
            {(liveAlert?.capacity_per_min ?? 0).toLocaleString()} people a minute.
          </Text>
        </VStack>
        <Text size="sm" color={accentColor} fontWeight="$bold" mt="$2">
          Do not join this crowd. Wait where you are, or leave by another route.
        </Text>
        <MotionButton
          label="Close"
          variant="outline"
          color={borderColor}
          textColor={textPrimary}
          mt="$4"
          onPress={() => setAlertOpen(false)}
        />
      </Sheet>


      {/* Settings */}
      <Sheet visible={settingsOpen} title="Settings" onClose={() => setSettingsOpen(false)}>
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
