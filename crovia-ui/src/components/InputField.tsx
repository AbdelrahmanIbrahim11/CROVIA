import React, { useState } from 'react';
import { StyleSheet, Text, TextInput, TextInputProps, View } from 'react-native';
import { useTheme } from '../theme/ThemeProvider';
import { curve, radius, space, type } from '../theme/tokens';

type Status = 'default' | 'error' | 'success';

type Props = TextInputProps & {
  label: string;
  helper?: string;
  status?: Status;
};

export function InputField({ label, helper, status = 'default', ...rest }: Props) {
  const { colors } = useTheme();
  const [focused, setFocused] = useState(false);

  const borderColor =
    status === 'error'
      ? colors.danger
      : status === 'success'
      ? colors.safe
      : focused
      ? colors.borderFocus
      : colors.borderSubtle;

  const helperColor =
    status === 'error' ? colors.danger : status === 'success' ? colors.safe : colors.textMuted;

  return (
    <View style={styles.wrap}>
      <Text style={[type.label, { color: colors.textSecondary }]}>{label}</Text>
      <TextInput
        {...rest}
        onFocus={(e) => {
          setFocused(true);
          rest.onFocus?.(e);
        }}
        onBlur={(e) => {
          setFocused(false);
          rest.onBlur?.(e);
        }}
        placeholderTextColor={colors.textMuted}
        style={[
          styles.input,
          type.body,
          {
            backgroundColor: colors.bgInset,
            borderColor,
            borderWidth: focused || status !== 'default' ? 1.5 : 1,
            color: colors.textPrimary,
          },
        ]}
      />
      {helper ? <Text style={[type.caption, { color: helperColor }]}>{helper}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: space.sm },
  input: {
    borderRadius: radius.md,
    ...curve,
    paddingHorizontal: 16,
    paddingVertical: 14,
    minHeight: 52,
  },
});
