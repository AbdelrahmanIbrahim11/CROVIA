import React, { useCallback, useEffect, useState } from 'react';
import { ScrollView } from 'react-native';
import {
  Box,
  Text,
  VStack,
  HStack,
  Input,
  InputField,
} from '@gluestack-ui/themed';
import { Sheet } from './Chrome';
import { MotionButton } from './MotionButton';
import { Incident, acknowledgeIncident, closeIncident, fetchIncidents } from '../api';
import { zoneById } from '../geo';

/**
 * What an authority does about an alarm.
 *
 * The point of this panel is the middle state. Before it existed an alarm was
 * either live or gone, and there was no way to tell an alarm nobody had seen
 * from one a safety officer was already handling. Both looked identical on the
 * map, which is the situation where two teams go to the same gate and none goes
 * to the other one.
 *
 * So there are three states and they are kept distinct:
 *
 *   unanswered    nobody has taken it. This is what the badge counts.
 *   acknowledged  a named person has it. The crowd is still there.
 *   closed        it is over, and what was done about it is on the record.
 */

const accentColor = '#F2A93B';
const cardBg = '#111420';
const textPrimary = '#F0F0F0';
const textMuted = '#9CA3AF';
const borderColor = '#2A314A';

export function useIncidents(pollMs = 10000) {
  const [incidents, setIncidents] = useState<Incident[]>([]);

  const refresh = useCallback(async () => {
    setIncidents(await fetchIncidents());
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, pollMs);
    return () => clearInterval(id);
  }, [refresh, pollMs]);

  // The badge counts only alarms nobody has taken. Counting every open incident
  // would keep a number on screen while a colleague is already dealing with it,
  // and a number that never clears is a number people stop reading.
  const unanswered = incidents.filter((i) => i.open && !i.acknowledged).length;

  return { incidents, unanswered, refresh };
}

export function IncidentPanel({
  visible,
  onClose,
  incidents,
  onChanged,
}: {
  visible: boolean;
  onClose: () => void;
  incidents: Incident[];
  onChanged: () => void;
}) {
  const [closingId, setClosingId] = useState<string | null>(null);
  const [action, setAction] = useState('');
  const [busy, setBusy] = useState<string | null>(null);

  async function ack(id: string) {
    setBusy(id);
    await acknowledgeIncident(id);
    setBusy(null);
    onChanged();
  }

  async function finish(id: string) {
    setBusy(id);
    await closeIncident(id, action.trim());
    setBusy(null);
    setClosingId(null);
    setAction('');
    onChanged();
  }

  return (
    <Sheet visible={visible} title="Incidents" onClose={onClose}>
      {incidents.length === 0 ? (
        <Text size="sm" color={textMuted}>
          No alarms have been recorded yet.
        </Text>
      ) : null}

      <ScrollView style={{ maxHeight: 420 }} contentContainerStyle={{ gap: 12 }}>
        {incidents.map((i) => {
          const name = zoneById[i.zone_id]?.label ?? i.zone_id;
          const state = !i.open ? 'closed' : i.acknowledged ? 'acknowledged' : 'unanswered';
          const tint =
            state === 'closed' ? '#00C851' : state === 'acknowledged' ? accentColor : '#ff4444';

          return (
            <Box
              key={i.id}
              bg={cardBg}
              borderWidth={1}
              borderColor={borderColor}
              borderLeftWidth={3}
              borderLeftColor={tint}
              borderRadius="$xl"
              p="$4"
            >
              <HStack alignItems="flex-start" justifyContent="space-between">
                <VStack flex={1} mr="$2" space="xs">
                  <Text size="md" fontWeight="$bold" color={textPrimary}>{name}</Text>
                  <Text size="xs" color={textMuted}>{i.reason}</Text>
                </VStack>
                <Text size="xs" color={tint} fontWeight="$bold">
                  {state.toUpperCase()}
                </Text>
              </HStack>

              {i.people_low != null ? (
                <Text size="xs" color={textMuted} mt="$2">
                  {i.people_low.toLocaleString()}–{i.people_high?.toLocaleString()} people
                  {i.duration_s != null ? ` · lasted ${Math.round(i.duration_s / 60)} min` : ''}
                </Text>
              ) : null}

              {i.acknowledged_by ? (
                <Text size="xs" color={accentColor} mt="$1">
                  Taken by {i.acknowledged_by}
                </Text>
              ) : null}

              {i.closed_by ? (
                <Text size="xs" color="#00C851" mt="$1">
                  Closed by {i.closed_by}
                  {i.action_taken ? ` — ${i.action_taken}` : ''}
                </Text>
              ) : null}

              {closingId === i.id ? (
                <VStack space="xs" mt="$3">
                  <Text size="xs" color={textPrimary} fontWeight="$bold">
                    What did you do about it?
                  </Text>
                  <Input variant="outline" size="lg" borderRadius="$lg" borderColor={borderColor} $focus-borderColor={accentColor}>
                    <InputField
                      value={action}
                      onChangeText={setAction}
                      placeholder="Opened the east gate and held the tram"
                      color={textPrimary}
                      placeholderTextColor="#6B7280"
                    />
                  </Input>
                  <HStack space="md" mt="$1">
                    <MotionButton
                      label={busy === i.id ? 'Closing…' : 'Close incident'}
                      color="#00C851"
                      textColor="#161A28"
                      flex={1}
                      onPress={() => finish(i.id)}
                    />
                    <MotionButton
                      label="Cancel"
                      variant="outline"
                      color={borderColor}
                      textColor={textPrimary}
                      flex={1}
                      onPress={() => { setClosingId(null); setAction(''); }}
                    />
                  </HStack>
                </VStack>
              ) : i.open ? (
                <HStack space="md" mt="$3">
                  {!i.acknowledged ? (
                    <MotionButton
                      label={busy === i.id ? 'Taking…' : 'I am dealing with this'}
                      color={accentColor}
                      textColor="#161A28"
                      flex={1}
                      onPress={() => ack(i.id)}
                    />
                  ) : null}
                  <MotionButton
                    label="Close"
                    variant="outline"
                    color={borderColor}
                    textColor={textPrimary}
                    flex={1}
                    onPress={() => setClosingId(i.id)}
                  />
                </HStack>
              ) : null}
            </Box>
          );
        })}
      </ScrollView>
    </Sheet>
  );
}
