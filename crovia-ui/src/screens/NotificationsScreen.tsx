import React, { useCallback, useEffect, useState } from 'react';
import { RefreshControl, ScrollView } from 'react-native';
import { VStack, Text, Box, HStack, Pressable } from '@gluestack-ui/themed';
import { Warning, fetchMyWarnings, markWarningRead } from '../api';
import { zoneById } from '../geo';

/**
 * The warnings this person was actually sent.
 *
 * This screen used to list five made-up notices that never changed. Now it
 * shows what the backend really sent to this account, and nothing else: the
 * server works out whose warnings these are from the token, so there is no id
 * to pass and no way to read somebody else's.
 *
 * An empty list is a good outcome and says so, rather than looking broken.
 */

const bgColor = '#161A28';
const cardBg = '#1E2336';
const accentColor = '#F2A93B';
const textPrimary = '#F0F0F0';
const textMuted = '#9CA3AF';
const borderColor = '#2A314A';

function whenText(iso: string | null): string {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  return hrs < 24 ? `${hrs} h ago` : `${Math.round(hrs / 24)} d ago`;
}

export function NotificationsScreen() {
  const [warnings, setWarnings] = useState<Warning[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setWarnings(await fetchMyWarnings());
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, [refresh]);

  async function open(w: Warning) {
    if (w.read) return;
    await markWarningRead(w.id);
    refresh();
  }

  return (
    <Box flex={1} bg={bgColor}>
      <ScrollView
        contentContainerStyle={{ padding: 24, paddingBottom: 100 }}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={refresh} tintColor={accentColor} />}
      >
        <VStack space="xl">
          <Text size="3xl" fontWeight="$bold" color={textPrimary} mb="$4">
            Alerts
          </Text>

          {!loading && warnings.length === 0 ? (
            <Box bg={cardBg} borderWidth={1} borderColor={borderColor} borderRadius="$xl" p="$6">
              <Text size="md" fontWeight="$bold" color={textPrimary}>
                Nothing to report
              </Text>
              <Text size="sm" color={textMuted} mt="$2">
                You have not been warned about any crowd. Warnings appear here the
                moment CROVIA sends you one.
              </Text>
            </Box>
          ) : null}

          <VStack space="md">
            {warnings.map((w) => (
              <Pressable key={w.id} onPress={() => open(w)} accessibilityRole="button">
                <Box
                  bg={cardBg}
                  borderWidth={1}
                  borderColor={w.read ? borderColor : '#ff4444'}
                  borderLeftWidth={3}
                  borderLeftColor={w.read ? borderColor : '#ff4444'}
                  borderRadius="$xl"
                  p="$4"
                >
                  <HStack alignItems="flex-start" justifyContent="space-between">
                    <Text size="md" fontWeight="$bold" color={textPrimary} flex={1} mr="$2">
                      {w.title}
                    </Text>
                    <Text size="xs" color={textMuted}>{whenText(w.sent_at)}</Text>
                  </HStack>
                  <Text size="sm" color={textMuted} mt="$2" lineHeight="$md">
                    {w.body}
                  </Text>
                  <Text size="xs" color={accentColor} mt="$2">
                    {zoneById[w.zone_id]?.label ?? w.zone_id}
                    {w.read ? '' : ' · tap to mark as read'}
                  </Text>
                </Box>
              </Pressable>
            ))}
          </VStack>
        </VStack>
      </ScrollView>
    </Box>
  );
}
