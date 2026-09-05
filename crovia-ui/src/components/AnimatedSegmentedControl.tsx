import React, { useRef, useState, useEffect } from 'react';
import { Animated, PanResponder, LayoutChangeEvent } from 'react-native';
import { Box, Text, HStack, Pressable } from '@gluestack-ui/themed';

export function AnimatedSegmentedControl<T extends string>({
  options,
  value,
  onChange,
  activeColor = '#F2A93B',
  inactiveColor = '#111420',
  textColor = '#F0F0F0',
  activeTextColor = '#161A28',
}: {
  options: { key: T; label: string }[];
  value: T;
  onChange: (val: T) => void;
  activeColor?: string;
  inactiveColor?: string;
  textColor?: string;
  activeTextColor?: string;
}) {
  const [containerWidth, setContainerWidth] = useState(0);
  const slideAnim = useRef(new Animated.Value(0)).current;
  
  const currentIndex = options.findIndex(o => o.key === value);
  const itemWidth = containerWidth > 0 ? containerWidth / options.length : 0;

  // Move the pill when value changes externally
  useEffect(() => {
    if (itemWidth > 0) {
      Animated.spring(slideAnim, {
        toValue: currentIndex * itemWidth,
        useNativeDriver: false, // Must be false for PanResponder tracking on some platforms
        tension: 60,
        friction: 8
      }).start();
    }
  }, [currentIndex, itemWidth]);

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: () => {
        slideAnim.setOffset((slideAnim as any)._value);
        slideAnim.setValue(0);
      },
      onPanResponderMove: Animated.event(
        [null, { dx: slideAnim }],
        { useNativeDriver: false }
      ),
      onPanResponderRelease: (e, gestureState) => {
        slideAnim.flattenOffset();
        const currentX = (slideAnim as any)._value;
        let targetIndex = Math.round(currentX / itemWidth);
        
        // Clamp to boundaries
        if (targetIndex < 0) targetIndex = 0;
        if (targetIndex > options.length - 1) targetIndex = options.length - 1;
        
        // Animate to snap position
        Animated.spring(slideAnim, {
          toValue: targetIndex * itemWidth,
          useNativeDriver: false,
          tension: 60,
          friction: 8
        }).start();

        // Fire onChange if the target changed
        if (targetIndex !== currentIndex) {
          onChange(options[targetIndex].key);
        }
      },
    })
  ).current;

  return (
    <Box 
      bg={inactiveColor} 
      p="$1" 
      borderRadius="$full" 
      position="relative"
      onLayout={(e: LayoutChangeEvent) => setContainerWidth(e.nativeEvent.layout.width - 8)} // padding is roughly 8px total
    >
      {itemWidth > 0 && (
        <Animated.View
          style={{
            position: 'absolute',
            top: 4,
            left: 4,
            bottom: 4,
            width: itemWidth,
            backgroundColor: activeColor,
            borderRadius: 999,
            transform: [{ translateX: slideAnim }]
          }}
          {...panResponder.panHandlers}
        />
      )}
      
      <HStack space="xs" position="relative" pointerEvents="box-none">
        {options.map((o, idx) => {
          const on = o.key === value;
          return (
            <Pressable
              key={o.key}
              onPress={() => onChange(o.key)}
              flex={1}
              alignItems="center"
              py="$2"
              borderRadius="$full"
            >
              <Text size="sm" fontWeight={on ? "$bold" : "$medium"} color={on ? activeTextColor : textColor}>
                {o.label}
              </Text>
            </Pressable>
          );
        })}
      </HStack>
    </Box>
  );
}
