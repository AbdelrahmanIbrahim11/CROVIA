import React from 'react';
import { KeyboardAvoidingView, Platform, Image as RNImage } from 'react-native';
import {
  Box,
  Text,
  VStack,
  HStack,
  Input,
  InputField as GluestackInputField,
  Pressable,
  ScrollView,
  Center,
} from '@gluestack-ui/themed';
import { MotionButton } from '../components/MotionButton';
import { DropInText, TypewriterText } from '../components/AnimatedText';

export function SignUpScreen({
  onCreate,
  onBack,
}: {
  onCreate: () => void;
  onBack: () => void;
}) {
  const bgColor = '#161A28';
  const accentColor = '#F2A93B';
  const cardBg = '#1E2336';
  const textPrimary = '#F0F0F0';
  const textMuted = '#9CA3AF';

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: bgColor }}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: 'center' }} keyboardShouldPersistTaps="handled">
        
        <Center px="$6" py="$12">
          {/* Logo Image */}
          <RNImage 
            source={require('../../assets/logo.png')} 
            style={{ width: 300, height: 85, resizeMode: 'contain', marginBottom: 40 }} 
          />

          <Box 
            bg={cardBg} 
            p="$8" 
            borderRadius="$2xl" 
            width="100%" 
            maxWidth={450}
            borderWidth={1}
            borderColor="#2A314A"
            shadowColor="#000"
            shadowOffset={{ width: 0, height: 20 }}
            shadowOpacity={0.4}
            shadowRadius={20}
            elevation={15}
          >
            <VStack space="2xl">
              <VStack space="xs" alignItems="center">
                <DropInText text="Create your citizen account" color={textPrimary} />
                <TypewriterText text="Join the Crovia network to stay safe." color={textMuted} delay={600} />
              </VStack>

              <VStack space="xl">
                <HStack space="md">
                  <VStack space="xs" flex={1}>
                    <Text size="sm" fontWeight="$medium" color={textPrimary}>First name</Text>
                    <Input variant="outline" size="xl" borderRadius="$lg" borderColor="#333A54" $focus-borderColor={accentColor}>
                      <GluestackInputField placeholder="Nour" color={textPrimary} placeholderTextColor="#6B7280" />
                    </Input>
                  </VStack>
                  <VStack space="xs" flex={1}>
                    <Text size="sm" fontWeight="$medium" color={textPrimary}>Last name</Text>
                    <Input variant="outline" size="xl" borderRadius="$lg" borderColor="#333A54" $focus-borderColor={accentColor}>
                      <GluestackInputField placeholder="Mahmoud" color={textPrimary} placeholderTextColor="#6B7280" />
                    </Input>
                  </VStack>
                </HStack>

                <VStack space="xs">
                  <Text size="sm" fontWeight="$medium" color={textPrimary}>Phone number</Text>
                  <Input variant="outline" size="xl" borderRadius="$lg" borderColor="#333A54" $focus-borderColor={accentColor}>
                    <GluestackInputField placeholder="+20 100 000 0000" keyboardType="phone-pad" color={textPrimary} placeholderTextColor="#6B7280" />
                  </Input>
                </VStack>

                <VStack space="xs">
                  <Text size="sm" fontWeight="$medium" color={textPrimary}>Password</Text>
                  <Input variant="outline" size="xl" borderRadius="$lg" borderColor="#333A54" $focus-borderColor={accentColor}>
                    <GluestackInputField placeholder="••••••••" secureTextEntry color={textPrimary} placeholderTextColor="#6B7280" />
                  </Input>
                </VStack>

                <MotionButton 
                  label="Create account"
                  color={accentColor}
                  textColor="#161A28"
                  mt="$2"
                  onPress={onCreate}
                />
              </VStack>

              <HStack space="sm" justifyContent="center" alignItems="center" mt="$2">
                <Text size="sm" color={textMuted}>
                  Already have an account?
                </Text>
                <Pressable onPress={onBack}>
                  <Text size="sm" color={accentColor} fontWeight="$bold">
                    Sign in
                  </Text>
                </Pressable>
              </HStack>
            </VStack>
          </Box>
        </Center>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
