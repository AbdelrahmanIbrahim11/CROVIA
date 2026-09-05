import React from 'react';
import { ScrollView } from 'react-native';
import { VStack, Text, Box } from '@gluestack-ui/themed';
import { NotificationCard } from '../components/NotificationCard';
import { notifications } from '../data';

const bgColor = '#161A28';
const textPrimary = '#F0F0F0';

export function NotificationsScreen() {
  return (
    <Box flex={1} bg={bgColor}>
      <ScrollView contentContainerStyle={{ padding: 24, paddingBottom: 100 }}>
        <VStack space="xl">
          <Text size="3xl" fontWeight="$bold" color={textPrimary} mb="$4">
            Alerts
          </Text>
          <VStack space="md">
            {notifications.map((n) => (
              <NotificationCard key={n.id} item={n} />
            ))}
          </VStack>
        </VStack>
      </ScrollView>
    </Box>
  );
}
