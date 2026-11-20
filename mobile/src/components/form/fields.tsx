/**
 * Text inputs for forms. Each shows its label, an optional hint, and the error for that field,
 * whether the app found it (an amount it can't read) or the backend did (a 422).
 */
import type { ReactNode } from 'react';
import { StyleSheet, Text, TextInput, type TextInputProps, View } from 'react-native';

import { colors, spacing } from '../theme';

type ShellProps = {
  label: string;
  error?: string;
  hint?: string;
  children: ReactNode;
};

/** Label above, then the control, then a hint or the field's error. */
export function FieldShell({ label, error, hint, children }: ShellProps) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      {children}
      {hint && !error ? <Text style={styles.hint}>{hint}</Text> : null}
      {error ? (
        <Text accessibilityLabel={`${label}: ${error}`} style={styles.error}>
          {error}
        </Text>
      ) : null}
    </View>
  );
}

type TextFieldProps = Omit<TextInputProps, 'style' | 'value' | 'onChangeText'> & {
  label: string;
  value: string;
  onChangeText: (text: string) => void;
  error?: string;
  hint?: string;
  /** Shown inside the box before the text, such as "$". */
  prefix?: string;
};

export function TextField({ label, error, hint, prefix, ...input }: TextFieldProps) {
  return (
    <FieldShell label={label} error={error} hint={hint}>
      <View style={[styles.box, error ? styles.boxError : null]}>
        {prefix ? <Text style={styles.prefix}>{prefix}</Text> : null}
        <TextInput accessibilityLabel={label} style={styles.input} autoCorrect={false} {...input} />
      </View>
    </FieldShell>
  );
}

type MoneyFieldProps = Omit<TextFieldProps, 'keyboardType' | 'prefix'> & {
  /** Only a balance can be negative (overdrawn). */
  allowNegative?: boolean;
};

/**
 * Dollars and cents as typed text. The form converts it with `parseMoney`, which reads the
 * digits as text and never through a float.
 */
export function MoneyField({
  allowNegative = false,
  placeholder = '0.00',
  ...props
}: MoneyFieldProps) {
  return (
    <TextField
      prefix="$"
      placeholder={placeholder}
      // The decimal pad has no minus key, so a field that allows one needs punctuation.
      keyboardType={allowNegative ? 'numbers-and-punctuation' : 'decimal-pad'}
      autoCapitalize="none"
      {...props}
    />
  );
}

/** Digits only, such as a priority or a day of the month. */
export function WholeNumberField(props: Omit<TextFieldProps, 'keyboardType'>) {
  return <TextField keyboardType="number-pad" {...props} />;
}

export const fieldStyles = StyleSheet.create({
  box: {
    alignItems: 'center',
    borderColor: colors.border,
    borderRadius: 8,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    minHeight: 44,
    paddingHorizontal: spacing.m,
  },
  boxError: { borderColor: colors.error, borderWidth: 1 },
});

const styles = StyleSheet.create({
  field: { gap: spacing.xs, marginTop: spacing.m },
  label: { color: colors.label, fontSize: 14 },
  hint: { color: colors.muted, fontSize: 13 },
  error: { color: colors.error, fontSize: 14 },
  ...fieldStyles,
  prefix: { color: colors.muted, fontSize: 17, marginRight: spacing.xs },
  input: { color: colors.text, flex: 1, fontSize: 17, paddingVertical: 10 },
});
