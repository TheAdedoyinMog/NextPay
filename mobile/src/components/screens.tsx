/**
 * Layout and the three states every data screen has besides success: loading, error, empty.
 */
import type { ReactNode } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { ApiError, errorMessage } from '@/api/client';

import { ActionButton } from './form/actions';
import { colors, spacing } from './theme';

/** A scrolling screen whose content stays above the keyboard. */
export function Screen({ children }: { children: ReactNode }) {
  return (
    <KeyboardAvoidingView style={styles.fill} behavior="padding">
      <ScrollView
        style={styles.fill}
        contentContainerStyle={styles.content}
        contentInsetAdjustmentBehavior="automatic"
        keyboardShouldPersistTaps="handled"
      >
        {children}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <View style={styles.centered}>
      <ActivityIndicator />
      <Text style={styles.muted}>{label}</Text>
    </View>
  );
}

/** No answer reached us: the network, not the session, so say the user is still signed in. */
export function isNoResponse(error: unknown): boolean {
  return error instanceof ApiError && error.status === 0;
}

type ErrorStateProps = {
  error: unknown;
  onRetry: () => void;
  isRetrying?: boolean;
};

export function ErrorState({ error, onRetry, isRetrying = false }: ErrorStateProps) {
  return (
    <View style={styles.block}>
      <Text accessibilityRole="alert" style={styles.error}>
        {errorMessage(error)}
      </Text>
      {isNoResponse(error) ? <Text style={styles.muted}>You’re still signed in.</Text> : null}
      <ActionButton
        title="Try again"
        pendingTitle="Trying…"
        isPending={isRetrying}
        variant="secondary"
        onPress={onRetry}
      />
    </View>
  );
}

type EmptyStateProps = {
  title: string;
  message?: string;
  actionLabel?: string;
  onAction?: () => void;
};

export function EmptyState({ title, message, actionLabel, onAction }: EmptyStateProps) {
  return (
    <View style={styles.block}>
      <Text style={styles.emptyTitle}>{title}</Text>
      {message ? <Text style={styles.muted}>{message}</Text> : null}
      {actionLabel && onAction ? <ActionButton title={actionLabel} onPress={onAction} /> : null}
    </View>
  );
}

type RowProps = {
  title: string;
  subtitle?: string;
  /** On the right, such as an amount. */
  detail?: string;
  onPress?: () => void;
  accessibilityLabel?: string;
};

/** One item in a list. Tappable when it has `onPress`. */
export function ListRow({ title, subtitle, detail, onPress, accessibilityLabel }: RowProps) {
  const content = (
    <>
      <View style={styles.rowText}>
        <Text style={styles.rowTitle}>{title}</Text>
        {subtitle ? <Text style={styles.muted}>{subtitle}</Text> : null}
      </View>
      {detail ? <Text style={styles.rowDetail}>{detail}</Text> : null}
      {onPress ? <Text style={styles.chevron}>›</Text> : null}
    </>
  );
  if (!onPress) {
    return <View style={styles.row}>{content}</View>;
  }
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? title}
      onPress={onPress}
      style={({ pressed }) => [styles.row, pressed ? styles.pressed : null]}
    >
      {content}
    </Pressable>
  );
}

/** A heading over a group of rows. */
export function SectionTitle({ children }: { children: ReactNode }) {
  return <Text style={styles.sectionTitle}>{children}</Text>;
}

export function Paragraph({ children }: { children: ReactNode }) {
  return <Text style={styles.paragraph}>{children}</Text>;
}

const styles = StyleSheet.create({
  fill: { backgroundColor: colors.background, flex: 1 },
  content: { padding: spacing.xl, paddingBottom: 48 },
  centered: { alignItems: 'center', gap: spacing.s, paddingVertical: spacing.xl },
  block: { gap: spacing.s, paddingVertical: spacing.m },
  muted: { color: colors.muted, fontSize: 15 },
  error: { color: colors.error, fontSize: 15 },
  emptyTitle: { color: colors.text, fontSize: 17, fontWeight: '600' },
  row: {
    alignItems: 'center',
    borderBottomColor: colors.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    gap: spacing.s,
    minHeight: 56,
    paddingVertical: spacing.m,
  },
  pressed: { opacity: 0.6 },
  rowText: { flex: 1, gap: 2 },
  rowTitle: { color: colors.text, fontSize: 17 },
  rowDetail: { color: colors.text, fontSize: 17, fontVariant: ['tabular-nums'] },
  chevron: { color: colors.muted, fontSize: 22 },
  sectionTitle: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: '600',
    marginTop: spacing.xl,
    textTransform: 'uppercase',
  },
  paragraph: { color: colors.text, fontSize: 16, lineHeight: 22, marginTop: spacing.s },
});
