/** Submitting, form-level errors, and confirming a delete. */
import { ActivityIndicator, Alert, Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, spacing } from '../theme';

/** An error about the whole form: a server error, a conflict, or a 422 summary. */
export function FormError({ message }: { message: string | null }) {
  if (!message) {
    return null;
  }
  return (
    <Text accessibilityRole="alert" style={styles.formError}>
      {message}
    </Text>
  );
}

type ButtonProps = {
  title: string;
  onPress: () => void;
  disabled?: boolean;
  /** Shows a spinner and `pendingTitle`, and ignores presses. */
  isPending?: boolean;
  pendingTitle?: string;
  variant?: 'primary' | 'secondary' | 'danger';
  /** For VoiceOver when several buttons share a title, such as "Mark Rent paid". */
  accessibilityLabel?: string;
};

/** The main action on a screen. While pending it can't be pressed again, so no double submit. */
export function ActionButton({
  title,
  onPress,
  disabled = false,
  isPending = false,
  pendingTitle = 'Saving…',
  variant = 'primary',
  accessibilityLabel,
}: ButtonProps) {
  const inactive = disabled || isPending;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={isPending ? pendingTitle : (accessibilityLabel ?? title)}
      accessibilityState={{ disabled: inactive, busy: isPending }}
      disabled={inactive}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        styles[variant],
        inactive ? styles.inactive : null,
        pressed ? styles.pressed : null,
      ]}
    >
      <View style={styles.row}>
        {isPending ? (
          <ActivityIndicator color={variant === 'primary' ? colors.onAccent : colors.accent} />
        ) : null}
        <Text style={[styles.buttonText, styles[`${variant}Text`]]}>
          {isPending ? pendingTitle : title}
        </Text>
      </View>
    </Pressable>
  );
}

type ConfirmDelete = {
  title: string;
  message: string;
  confirmLabel?: string;
  onConfirm: () => void;
};

/** The native iOS alert, with Cancel and a red confirm button. */
export function confirmDelete({
  title,
  message,
  confirmLabel = 'Delete',
  onConfirm,
}: ConfirmDelete) {
  Alert.alert(title, message, [
    { text: 'Cancel', style: 'cancel' },
    { text: confirmLabel, style: 'destructive', onPress: onConfirm },
  ]);
}

const styles = StyleSheet.create({
  formError: { color: colors.error, fontSize: 15, marginTop: spacing.l },
  button: {
    alignItems: 'center',
    borderRadius: 10,
    marginTop: spacing.l,
    minHeight: 48,
    justifyContent: 'center',
    paddingHorizontal: spacing.l,
  },
  row: { alignItems: 'center', flexDirection: 'row', gap: spacing.s },
  primary: { backgroundColor: colors.accent },
  secondary: { backgroundColor: colors.surface },
  danger: { backgroundColor: colors.surface },
  inactive: { opacity: 0.5 },
  pressed: { opacity: 0.8 },
  buttonText: { fontSize: 17, fontWeight: '600' },
  primaryText: { color: colors.onAccent },
  secondaryText: { color: colors.accent },
  dangerText: { color: colors.danger },
});
