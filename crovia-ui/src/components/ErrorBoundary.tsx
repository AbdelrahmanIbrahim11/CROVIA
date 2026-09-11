import React from 'react';
import { ScrollView } from 'react-native';
import { Box, Text, VStack } from '@gluestack-ui/themed';

/**
 * Show what broke instead of a blank screen.
 *
 * When a React screen throws, React unmounts the whole tree and the page goes
 * white. On a phone there is no console to open, so the failure is invisible
 * and indistinguishable from a slow load or a bad network.
 *
 * A crowd-safety app that shows nothing is worse than one that shows an error,
 * because a person staring at an empty screen has no reason to think anything
 * is wrong.
 */

const bgColor = '#161A28';
const cardBg = '#1E2336';
const textPrimary = '#F0F0F0';
const textMuted = '#9CA3AF';

type State = { error: Error | null; info: string };

export class ErrorBoundary extends React.Component<
  { children: React.ReactNode; label?: string },
  State
> {
  state: State = { error: null, info: '' };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Also printed, so it reaches the Metro terminal during development.
    // eslint-disable-next-line no-console
    console.error('CROVIA screen crashed:', error, info.componentStack);
    this.setState({ info: info.componentStack ?? '' });
  }

  render() {
    const { error, info } = this.state;
    if (!error) return this.props.children;

    return (
      <Box flex={1} bg={bgColor} p="$6">
        <ScrollView>
          <VStack space="lg">
            <Text size="2xl" fontWeight="$bold" color="#ff4444">
              This screen could not open
            </Text>
            <Text size="sm" color={textMuted}>
              {this.props.label
                ? `Something went wrong in ${this.props.label}.`
                : 'Something went wrong.'}{' '}
              The rest of the app still works — go back and try again.
            </Text>

            <Box bg={cardBg} borderRadius="$lg" p="$4">
              <Text size="sm" color={textPrimary} fontWeight="$bold">
                {error.name}: {error.message}
              </Text>
            </Box>

            {info ? (
              <Box bg={cardBg} borderRadius="$lg" p="$4">
                <Text size="xs" color={textMuted}>
                  {info.split('\n').slice(0, 12).join('\n')}
                </Text>
              </Box>
            ) : null}
          </VStack>
        </ScrollView>
      </Box>
    );
  }
}
