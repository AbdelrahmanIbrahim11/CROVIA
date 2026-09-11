import React, { useState } from 'react';
import { ScrollView } from 'react-native';
import { Box, Text, VStack, HStack, Pressable, Center } from '@gluestack-ui/themed';
import { AppHeader, Metric, Sheet } from '../components/Chrome';
import { Input, InputField } from '@gluestack-ui/themed';
import { LatLon } from '../geo';
import { CityMap } from '../components/CityMap';
import { StatusChip } from '../components/StatusChip';
import { MotionButton } from '../components/MotionButton';
import { REGION } from '../data';
import { createOperatorZone, toOverlays } from '../api';
import { useLiveState } from '../useLiveState';
import { districts, zoneById } from '../geo';

type Tool = null | 'draw';

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
  const { state, connection } = useLiveState(5000);

  const [tool, setTool] = useState<Tool>(null);
  const [railOpen, setRailOpen] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Drawing a watch zone. The operator taps the map, then supplies the two
  // numbers the danger rule cannot work without: how wide the narrow point is
  // and how long it runs. Those are things a gate manager knows; guessing them
  // would produce a capacity figure with nothing behind it.
  const [draft, setDraft] = useState<LatLon | null>(null);
  const [label, setLabel] = useState('');
  const [widthM, setWidthM] = useState('6');
  const [lengthM, setLengthM] = useState('40');
  const [radiusM, setRadiusM] = useState('600');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (connection === 'connecting') {
    return (
      <Center flex={1} bg={bgColor}>
        <Text color={textMuted}>Connecting to CROVIA...</Text>
      </Center>
    );
  }

  const live = state ? toOverlays(state) : null;
  const districtOverlays = live?.districts ?? [];
  const zoneOverlays = live?.zones ?? [];
  const clusters = live?.clusters ?? [];

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
    : [];

  // Headline figures, from live state when there is any.
  const topScore = zoneRows.length ? Math.max(...zoneRows.map((z) => z.score)) : 0;
  const peopleWatched = state
    ? Math.round(
        Object.values(state.zones).reduce(
          (sum, v) => sum + (v ? (v.people_low + v.people_high) / 2 : 0),
          0,
        ),
      ).toLocaleString()
    : '0';

  const criticalCount = zoneRows.filter((z) => z.level === 'critical').length;



  /** Nearest district to the tapped point — that is the unit the network resolves to. */
  function nearestDistrict(p: LatLon): string {
    let best = districts[0];
    let bestD = Infinity;
    for (const d of districts) {
      const dx = (d.center.lon - p.lon) * Math.cos((p.lat * Math.PI) / 180);
      const dy = d.center.lat - p.lat;
      const dist = dx * dx + dy * dy;
      if (dist < bestD) { bestD = dist; best = d; }
    }
    return best.id;
  }

  async function saveZone() {
    if (!draft) return;
    setSaving(true);
    setSaveError(null);
    const res = await createOperatorZone({
      label: label.trim() || 'Operator zone',
      district_id: nearestDistrict(draft),
      lat: draft.lat,
      lon: draft.lon,
      radius_m: Number(radiusM),
      width_m: Number(widthM),
      length_m: Number(lengthM),
      created_by: roleLabel,
    });
    setSaving(false);
    if (!res.ok) { setSaveError(res.error); return; }
    setDraft(null);
    setLabel('');
    setTool(null);
  }

  const tools: { key: Exclude<Tool, null>; label: string; glyph: string }[] = [
    { key: 'draw', label: 'Draw zone', glyph: '▱' },
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
        unread={0}
        onSettings={() => setSettingsOpen(true)}
      />

      <Box flex={1}>
        <CityMap
          districts={districtOverlays}
          zones={zoneOverlays}
          clusters={clusters}
          showGrid
          onMapPress={tool === 'draw' ? (p) => { setDraft(p); setSaveError(null); } : undefined}
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
                Tap the place you want watched. You will be asked how wide its narrow point is.
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
                      : 'offline'
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
                  value={state ? String(topScore) : '—'}
                  label="Highest severity"
                  tint={topScore >= 75 ? '#ff4444' : accentColor}
                />
                <Metric
                  value={state ? peopleWatched : '—'}
                  label="People estimated"
                />
                <Metric
                  value={state ? String(state.monitored.panel) : '—'}
                  label="Panel devices"
                  tint="#33b5e5"
                />
              </HStack>

              <ScrollView contentContainerStyle={{ gap: 12, paddingTop: 16, paddingBottom: 24 }}>
                {zoneRows.map((z) => {
                  const lc = levelColors[z.level];
                  return (
                    <Box key={z.id}>
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
                    </Box>
                  );
                })}
              </ScrollView>
            </>
          ) : null}
        </VStack>
      </Box>

      {/* Drawing a watch zone */}
      <Sheet
        visible={!!draft}
        title="Watch this place"
        onClose={() => { setDraft(null); setSaveError(null); }}
      >
        <Text size="sm" color={textMuted}>
          CROVIA needs the narrow point, not the whole area. How many people a
          minute can get through decides everything else.
        </Text>

        <VStack space="xs">
          <Text size="xs" color={textPrimary} fontWeight="$bold">What is this place called?</Text>
          <Input variant="outline" size="xl" borderRadius="$lg" borderColor={borderColor} $focus-borderColor={accentColor}>
            <InputField
              value={label}
              onChangeText={setLabel}
              placeholder="West gate tonight"
              color={textPrimary}
              placeholderTextColor="#6B7280"
            />
          </Input>
        </VStack>

        <HStack space="md">
          <VStack space="xs" flex={1}>
            <Text size="xs" color={textPrimary} fontWeight="$bold">Narrowest width (m)</Text>
            <Input variant="outline" size="xl" borderRadius="$lg" borderColor={borderColor} $focus-borderColor={accentColor}>
              <InputField value={widthM} onChangeText={setWidthM} keyboardType="numeric"
                color={textPrimary} placeholderTextColor="#6B7280" />
            </Input>
          </VStack>
          <VStack space="xs" flex={1}>
            <Text size="xs" color={textPrimary} fontWeight="$bold">Length of it (m)</Text>
            <Input variant="outline" size="xl" borderRadius="$lg" borderColor={borderColor} $focus-borderColor={accentColor}>
              <InputField value={lengthM} onChangeText={setLengthM} keyboardType="numeric"
                color={textPrimary} placeholderTextColor="#6B7280" />
            </Input>
          </VStack>
        </HStack>

        <VStack space="xs">
          <Text size="xs" color={textPrimary} fontWeight="$bold">Watch circle radius (m)</Text>
          <Input variant="outline" size="xl" borderRadius="$lg" borderColor={borderColor} $focus-borderColor={accentColor}>
            <InputField value={radiusM} onChangeText={setRadiusM} keyboardType="numeric"
              color={textPrimary} placeholderTextColor="#6B7280" />
          </Input>
          <Text size="xs" color={textMuted}>
            600 m is the smallest the mobile network can resolve reliably. Smaller
            circles are refused rather than answered with numbers nobody should trust.
          </Text>
        </VStack>

        {/* The arithmetic, shown before saving, so the operator sees what they are creating */}
        <Box bg="rgba(242, 169, 59, 0.12)" borderWidth={1} borderColor={accentColor} borderRadius="$lg" p="$3">
          <Text size="sm" color={accentColor} fontWeight="$bold">
            {Number(widthM) > 0
              ? `${Math.round(Number(widthM) * 72).toLocaleString()} people a minute can pass`
              : 'Enter a width'}
          </Text>
          <Text size="xs" color={textMuted}>
            {Number(widthM) > 0 && Number(lengthM) > 0
              ? `Dangerous above about ${Math.round(
                  Number(widthM) * Number(lengthM) * 4,
                ).toLocaleString()} people standing in it.`
              : 'Width times 72 is how many get through each minute.'}
          </Text>
        </Box>

        {saveError ? (
          <Box bg="rgba(255, 68, 68, 0.12)" borderWidth={1} borderColor="#ff4444" borderRadius="$lg" p="$3">
            <Text size="sm" color="#ff4444">{saveError}</Text>
          </Box>
        ) : null}

        <HStack space="md" mt="$2">
          <MotionButton
            label={saving ? 'Adding…' : 'Watch this place'}
            color={accentColor}
            textColor="#161A28"
            flex={1}
            onPress={saveZone}
          />
          <MotionButton
            label="Cancel"
            variant="outline"
            color={borderColor}
            textColor={textPrimary}
            flex={1}
            onPress={() => { setDraft(null); setSaveError(null); }}
          />
        </HStack>
      </Sheet>

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
