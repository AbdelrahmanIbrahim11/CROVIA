import React, { useState } from 'react';
import { Pressable } from 'react-native';
import { Center, Box, Text } from '@gluestack-ui/themed';
import { AdminDashboardScreen } from './AdminDashboardScreen';
import { IncidentPanel, useIncidents } from '../components/IncidentPanel';

const accentColor = '#F2A93B';
const borderColor = '#2A314A';

/**
 * The authority view: everything operations can see, plus the ability to take
 * responsibility for an alarm and close it.
 *
 * The button used to be decorative. It now carries the number of alarms nobody
 * has taken yet, which is the only number a safety officer needs at a glance.
 */
export function PoliceDashboardScreen({ onSignOut }: { onSignOut: () => void }) {
  const { incidents, unanswered, refresh } = useIncidents();
  const [open, setOpen] = useState(false);

  return (
    <>
      <AdminDashboardScreen
        roleLabel="Authority"
        onSignOut={onSignOut}
        extraToolbar={
          <>
            <Box h={1} bg={borderColor} my="$1" mx="$2" />
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={
                unanswered > 0
                  ? `${unanswered} alarms waiting for someone to take them`
                  : 'Incidents'
              }
              onPress={() => setOpen(true)}
            >
              <Center
                w={42}
                h={42}
                borderRadius="$md"
                bg={unanswered > 0 ? 'rgba(255, 68, 68, 0.15)' : 'transparent'}
                borderColor={unanswered > 0 ? '#ff4444' : borderColor}
                borderWidth={1}
              >
                <Text
                  size="md"
                  fontWeight="$bold"
                  color={unanswered > 0 ? '#ff4444' : accentColor}
                >
                  {unanswered > 0 ? String(unanswered) : '!'}
                </Text>
              </Center>
            </Pressable>
          </>
        }
      />

      <IncidentPanel
        visible={open}
        onClose={() => setOpen(false)}
        incidents={incidents}
        onChanged={refresh}
      />
    </>
  );
}
