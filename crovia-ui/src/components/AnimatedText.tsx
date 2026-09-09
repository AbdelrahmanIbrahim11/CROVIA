import React, { useEffect, useRef, useState } from 'react';
import { Animated, Platform } from 'react-native';
import { Text } from '@gluestack-ui/themed';

export function DropInText({ 
  text, 
  delay = 0,
  size = "xl",
  fontWeight = "$bold",
  color
}: { 
  text: string;
  delay?: number;
  size?: any;
  fontWeight?: any;
  color?: string;
}) {
  const translateY = useRef(new Animated.Value(-30)).current;
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.sequence([
      Animated.delay(delay),
      Animated.parallel([
        Animated.spring(translateY, {
          toValue: 0,
          tension: 50,
          friction: 7,
          useNativeDriver: Platform.OS !== 'web',
        }),
        Animated.timing(opacity, {
          toValue: 1,
          duration: 500,
          useNativeDriver: Platform.OS !== 'web',
        })
      ])
    ]).start();
  }, [delay, opacity, translateY]);

  return (
    <Animated.View style={{ transform: [{ translateY }], opacity }}>
      <Text size={size} fontWeight={fontWeight} color={color}>
        {text}
      </Text>
    </Animated.View>
  );
}

export function TypewriterText({ 
  text, 
  delay = 500,
  speed = 40,
  size = "sm",
  color,
  textAlign = "center"
}: { 
  text: string;
  delay?: number;
  speed?: number;
  size?: any;
  color?: string;
  textAlign?: any;
}) {
  const [displayedText, setDisplayedText] = useState('');
  
  useEffect(() => {
    let timeout: ReturnType<typeof setTimeout>;
    
    // Initial delay before typing starts
    const initialTimeout = setTimeout(() => {
      let i = 0;
      const typeChar = () => {
        if (i < text.length) {
          setDisplayedText(text.substring(0, i + 1));
          i++;
          timeout = setTimeout(typeChar, speed);
        }
      };
      typeChar();
    }, delay);

    return () => {
      clearTimeout(initialTimeout);
      clearTimeout(timeout);
    };
  }, [text, delay, speed]);

  return (
    <Text size={size} color={color} textAlign={textAlign}>
      {displayedText}
      <Text opacity={displayedText.length === text.length ? 0 : 1}>|</Text>
    </Text>
  );
}
