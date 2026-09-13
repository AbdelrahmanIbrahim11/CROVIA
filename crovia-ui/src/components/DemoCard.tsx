/**
 * The control that starts and stops a simulated evening.
 *
 * Shared by the citizen map and the authority map on purpose. It began as a
 * block inside the citizen screen, so when the authority screen was opened
 * there was simply no way to start a demonstration from it - the same feature
 * existing in one place and not the other because of where the code happened
 * to live.
 *
 * It is labelled DEMONSTRATION throughout, because a screen showing invented
 * crowds without saying so is the one mistake this project cannot afford.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Box, Pressable, Text, VStack } from '@gluestack-ui/themed';

import { DemoState, fetchDemoState, startDemo, stopDemo } from '../api';

export function DemoCard({
  accentColor,
  borderColor,
  textMuted,
}: {
  accentColor: string;
  borderColor: string;
  textMuted: string;
}) {
  const [demo, setDemo] = useState<DemoState | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setDemo(await fetchDemoState());
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  const toggle = async () => {
    setBusy(true);
    try {
      if (demo?.running) await stopDemo();
      else await startDemo();
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const minutes = Math.round((demo?.simulated_seconds ?? 0) / 60);
  const alarms = demo?.alerts ?? 0;

  return (
    <VStack
      position="absolute"
      right="$4"
      bottom={260}
      bg="rgba(30, 35, 54, 0.94)"
      borderWidth={1}
      borderColor={demo?.running ? accentColor : borderColor}
      borderRadius="$lg"
      p="$3"
      space="xs"
      maxWidth={230}
    >
      <Text size="2xs" color={textMuted} letterSpacing={1}>
        DEMONSTRATION
      </Text>

      {demo?.running ? (
        <>
          <Text size="xs" color={accentColor} fontWeight="$bold">
            Simulated crowd running
          </Text>
          <Text size="2xs" color={textMuted} lineHeight="$xs">
            {minutes < 3
              ? 'People are heading for the stadium. No alarm yet — this is what calm looks like.'
              : alarms
                ? 'The crowd is trapped at the ramp. Check your notifications.'
                : 'The crowd is building at the exit ramp. Watch the map turn amber, then red.'}
          </Text>
          <Text size="2xs" color={textMuted}>
            {minutes} simulated min · {alarms} alarm{alarms === 1 ? '' : 's'}
          </Text>
        </>
      ) : (
        <Text size="2xs" color={textMuted} lineHeight="$xs">
          The city is calm. Start a simulated evening to watch a crowd build and
          a warning reach your phone.
        </Text>
      )}

      <Pressable onPress={toggle} disabled={busy} accessibilityRole="button">
        <Box
          bg={demo?.running ? '#ff4444' : accentColor}
          borderRadius="$md"
          py="$2"
          px="$3"
          opacity={busy ? 0.6 : 1}
          mt="$1"
        >
          <Text size="xs" fontWeight="$bold" color="#161A28" textAlign="center">
            {busy ? 'Please wait…' : demo?.running ? 'Stop demonstration' : 'Run demonstration'}
          </Text>
        </Box>
      </Pressable>
    </VStack>
  );
}
