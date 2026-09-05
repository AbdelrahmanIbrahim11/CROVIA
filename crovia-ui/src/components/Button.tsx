import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, ViewStyle } from 'react-native';
import { useTheme } from '../theme/ThemeProvider';
import { curve, radius, space, type } from '../theme/tokens';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'md' | 'sm';

type Props = {
  label: string;
  onPress?: () => void;
  variant?: Variant;
  size?: Size;
  disabled?: boolean;
  loading?: boolean;
  full?: boolean;
  style?: ViewStyle;
};

export function Button({
  label,
  onPress,
  variant = 'primary',
  size = 'md',
  disabled,
  loading,
  full,
  style,
}: Props) {
  const { colors } = useTheme();

  const skin: Record<Variant, { bg: string; fg: string; border?: string }> = {
    primary: { bg: colors.accent, fg: colors.textOnAccent },
    secondary: { bg: colors.bgElevated, fg: colors.textPrimary, border: colors.borderStrong },
    ghost: { bg: 'transparent', fg: colors.textSecondary },
    danger: { bg: colors.danger, fg: colors.textOnAccent },
  };

  const s = skin[variant];
  const pad = size === 'md' ? { v: 15, h: 24 } : { v: 10, h: 16 };

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled, busy: !!loading }}
      onPress={disabled || loading ? undefined : onPress}
      style={({ pressed }) => [
        styles.base,
        {
          backgroundColor: s.bg,
          borderColor: s.border ?? 'transparent',
          borderWidth: s.border ? 1 : 0,
          paddingVertical: pad.v,
          paddingHorizontal: pad.h,
          opacity: disabled ? 0.45 : pressed ? 0.82 : 1,
          alignSelf: full ? 'stretch' : 'flex-start',
        },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator size="small" color={s.fg} />
      ) : (
        <Text style={[size === 'md' ? type.button : type.label, { color: s.fg }]}>{label}</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    borderRadius: radius.md,
    ...curve,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: space.sm,
    minHeight: 50,
  },
});
