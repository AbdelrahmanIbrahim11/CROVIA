import React, { useRef } from 'react';
import { Animated, Platform, Pressable } from 'react-native';
import { Button as GluestackButton, ButtonText } from '@gluestack-ui/themed';

export function MotionButton({ 
  label, 
  onPress, 
  variant = 'solid', 
  color = '#F2A93B', 
  textColor = '#161A28',
  flex,
  mt
}: { 
  label: string; 
  onPress: () => void;
  variant?: 'solid' | 'outline';
  color?: string;
  textColor?: string;
  flex?: number;
  mt?: any;
}) {
  const scale = useRef(new Animated.Value(1)).current;

  const handleHoverIn = () => {
    if (Platform.OS === 'web') {
      Animated.spring(scale, { toValue: 1.05, friction: 5, useNativeDriver: true }).start();
    }
  };

  const handleHoverOut = () => {
    if (Platform.OS === 'web') {
      Animated.spring(scale, { toValue: 1, friction: 5, useNativeDriver: true }).start();
    }
  };

  const handlePressIn = () => {
    Animated.spring(scale, { toValue: 0.95, friction: 5, useNativeDriver: true }).start();
  };

  const handlePressOut = () => {
    Animated.spring(scale, { toValue: 1, friction: 5, useNativeDriver: true }).start();
  };

  // We wrap the Animated.View in a Pressable to handle standard press + web hover events
  return (
    <Pressable
      onPress={onPress}
      onPressIn={handlePressIn}
      onPressOut={handlePressOut}
      //@ts-ignore - onHoverIn is web only
      onHoverIn={handleHoverIn}
      //@ts-ignore - onHoverOut is web only
      onHoverOut={handleHoverOut}
      style={{ flex, marginTop: mt }}
    >
      <Animated.View style={{ transform: [{ scale }] }}>
        <GluestackButton 
          size="xl" 
          variant={variant} 
          bg={variant === 'solid' ? color : 'transparent'} 
          borderColor={color}
          borderRadius="$full" 
          pointerEvents="none" // let the Pressable handle touches
        >
          <ButtonText fontWeight="$bold" color={textColor}>{label}</ButtonText>
        </GluestackButton>
      </Animated.View>
    </Pressable>
  );
}
