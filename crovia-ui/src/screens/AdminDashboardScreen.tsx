import React, { useState } from 'react';
import { ScrollView } from 'react-native';
import { Box, Text, VStack, HStack, Pressable, Center } from '@gluestack-ui/themed';
import { AppHeader, Metric, Sheet } from '../components/Chrome';
import { CityMap } from '../components/CityMap';
import { StatusChip } from '../components/StatusChip';
import { MotionButton } from '../components/MotionButton';
import {
  blobs,
  clusters as demoClusters,
  districtOverlays as demoDistricts,
  markers,
  REGION,
  zoneOverlays as demoZones,
  zoneRows as demoRows,
} from '../data';
import { toOverlays } from '../api';
import { useLiveState } from '../useLiveState';
import { zoneById } from '../geo';

type Tool = null | 'draw' | 'reroute' | 'measure';

const bgColor = '#161A28';
const accentColor = '#F2A93B';
const cardBg = '#1E2336';
const textPrimary = '#F0F0F0';
const textMuted = '#9CA3AF';
const borderColor = '#2A314A';

const levelColors = {
  calm: { fg: '#00C851', bg: 'rgba(0, 200, 81, 0.15)' },
  watch: { fg: '#33b5e5', bg: 'rgba(51, 181, 229, 0.15)' },
  elevated: { fg: accentColor, bg: 'rgba(242, 169, 59, 0.15)' },
  critical: { fg: '#ff4444', bg: 'rgba(255, 68, 68, 0.15)' },
};

export function AdminDashboardScreen({
  onSignOut,
  extraToolbar,
  roleLabel = 'Surveillance',
}: {
  onSignOut: () => void;
  extraToolbar?: React.ReactNode;
  roleLabel?: string;
}) {
  // Live state when the backend is reachable, demo data when it is not. The
  // map itself never depends on the backend, because the geography comes from
  // the same file both sides read.
  const { state, connection } = useLiveState(5000);
  const live = state ? toOverlays(state) : null;
  const districtOverlays = live?.districts ?? demoDistricts;
  const zoneOverlays = live?.zones ?? demoZones;
  const clusters = live?.clusters ?? demoClusters;

  const zoneRows = state
    ? Object.entries(state.zones)
        .filter(([, v]) => v)
        .map(([id, v]) => ({
          id,
          name: zoneById[id]?.label ?? id,
          score: Math.round((v!.severity ?? 0) * 100),
          heads: `${Math.round(v!.people_low).toLocaleString()}–${Math.round(
            v!.people_high,
          ).toLocaleString()}`,
          level: (v!.dangerous
            ? 'critical'
            : v!.severity >= 0.5
            ? 'elevated'
            : v!.severity >= 0.2
            ? 'watch'
            : 'calm') as 'critical' | 'elevated' | 'watch' | 'calm',
        }))
        .sort((a, b) => b.score - a.score)
    : demoRows;

  // Headline figures, from live state when there is any.
  const topScore = zoneRows.length ? Math.max(...zoneRows.map((z) => z.score)) : 0;
  const peopleWatched = state
    ? Math.round(
        Object.values(state.zones).reduce(
          (sum, v) => sum + (v ? (v.people_low + v.people_high) / 2 : 0),
          0,
        ),
      ).toLocaleString()
    : '4,400';

  const criticalCount = zoneRows.filter((z) => z.level === 'critical').length;

  const [tool, setTool] = useState<Tool>(null);
  const [railOpen, setRailOpen] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const tools: { key: Exclude<Tool, null>; label: string; glyph: string }[] = [
    { key: 'draw', label: 'Draw zone', glyph: '▱' },
    { key: 'reroute', label: 'Reroute', glyph: '⤳' },
    { key: 'measure', label: 'Measure', glyph: '⇔' },
  ];

  return (
    <VStack flex={1} bg={bgColor}>
      <AppHeader
        region={REGION}
        subtitle={
          connection === 'live'
            ? `${roleLabel} · live · ${state?.monitored.panel ?? 0} panel devices · ${
                state?.spend.total ?? 0
              } API calls`
            : `${roleLabel} · demo data (backend offline)`
        }
        unread={3}
        onSettings={() => setSettingsOpen(true)}
      />

      <Box flex={1}>
        <CityMap
          markers={markers}
          blobs={blobs}
          districts={districtOverlays}
          zones={zoneOverlays}
          clusters={clusters}
          showGrid
        >
          {/* Editor toolbar */}
          <VStack
            position="absolute"
            top="$4"
            right="$4"
            bg="rgba(30, 35, 54, 0.9)"
            borderWidth={1}
            borderColor={borderColor}
            borderRadius="$lg"
            p="$1"
            space="xs"
          >
            {tools.map((t) => {
              const on = tool === t.key;
              return (
                <Pressable
                  key={t.key}
                  onPress={() => setTool(on ? null : t.key)}
                  accessibilityRole="button"
                  accessibilityState={{ selected: on }}
                >
                  <Center w={42} h={42} borderRadius="$md" bg={on ? 'rgba(242, 169, 59, 0.15)' : 'transparent'} borderColor={on ? accentColor : 'transparent'} borderWidth={1}>
                    <Text size="xl" color={on ? accentColor : textMuted}>{t.glyph}</Text>
                  </Center>
                </Pressable>
              );
            })}
            {extraToolbar}
          </VStack>

          {tool ? (
            <Box
              position="absolute"
              top="$4"
              left="$4"
              right={80}
              bg="rgba(242, 169, 59, 0.15)"
              borderWidth={1}
              borderColor={accentColor}
              borderRadius="$lg"
              p="$3"
            >
              <Text size="sm" color={accentColor} fontWeight="$bold">
                {tool === 'draw'
                  ? 'Tap the map to place polygon corners. Double-tap to close the zone.'
                  : tool === 'reroute'
                  ? 'Drag from a congested zone to the destination you want people sent towards.'
                  : 'Tap two points to measure the distance between them.'}
              </Text>
            </Box>
          ) : null}
        </CityMap>

        {/* Data rail */}
        <VStack
          position="absolute"
          left={0}
          right={0}
          bottom={0}
          bg={cardBg}
          borderTopWidth={1}
          borderTopColor={borderColor}
          borderTopLeftRadius="$3xl"
          borderTopRightRadius="$3xl"
          px="$6"
          pt="$4"
          pb="$6"
          maxHeight={railOpen ? '60%' : 70}
          shadowColor="#000"
          shadowOffset={{ width: 0, height: -5 }}
          shadowOpacity={0.3}
          shadowRadius={15}
          elevation={20}
        >
          <Pressable onPress={() => setRailOpen((o) => !o)} accessibilityRole="button">
            <HStack alignItems="center" pb="$4">
              <Text size="xl" fontWeight="$bold" color={textPrimary} flex={1}>Active regions</Text>
              <HStack space="md" alignItems="center">
                <StatusChip
                  level={criticalCount > 0 ? 'critical' : 'calm'}
                  label={
                    state
                      ? criticalCount > 0
                        ? `${criticalCount} critical`
                        : 'all clear'
                      : '1 critical'
                  }
                />
                <Text size="xl" color={textMuted}>{railOpen ? '⌄' : '⌃'}</Text>
              </HStack>
            </HStack>
          </Pressable>

          {railOpen ? (
            <>
              <HStack borderTopWidth={1} borderBottomWidth={1} borderColor={borderColor} py="$4" space="md">
                <Metric
                  value={state ? String(topScore) : '78'}
                  label="Highest severity"
                  tint={topScore >= 75 ? '#ff4444' : accentColor}
                />
                <Metric
                  value={state ? peopleWatched : '4,400'}
                  label="People estimated"
                />
                <Metric
                  value={state ? String(state.monitored.panel) : '12'}
                  label="Panel devices"
                  tint="#33b5e5"
                />
              </HStack>

              <ScrollView contentContainerStyle={{ gap: 12, paddingTop: 16, paddingBottom: 24 }}>
                {zoneRows.map((z) => {
                  const lc = levelColors[z.level];
                  return (
                    <Pressable key={z.id} accessibilityRole="button">
                      <HStack
                        alignItems="center"
                        borderWidth={1}
                        borderColor={borderColor}
                        borderRadius="$xl"
                        p="$3"
                        space="md"
                        bg="#111420"
                      >
                        <Center w={52} h={44} borderRadius="$lg" bg={lc.bg}>
                          <Text size="lg" fontWeight="$bold" color={lc.fg}>{z.score}</Text>
                        </Center>
                        <VStack flex={1} space="xs">
                          <Text size="md" fontWeight="$bold" color={textPrimary} numberOfLines={1}>{z.name}</Text>
                          <Text size="xs" color={textMuted}>{z.heads} people in zone</Text>
                        </VStack>
                        <StatusChip level={z.level} />
                      </HStack>
                    </Pressable>
                  );
                })}
              </ScrollView>
            </>
          ) : null}
        </VStack>
      </Box>

      <Sheet visible={settingsOpen} title="Settings" onClose={() => setSettingsOpen(false)}>
        <Text size="sm" color={textMuted}>
          Signed in as an operations account for the pilot.
        </Text>
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
