/** The current balance, a form to update it, and recent history. */
import { useState } from 'react';
import { StyleSheet, Text } from 'react-native';

import {
  EmptyState,
  ErrorState,
  ListRow,
  LoadingState,
  Paragraph,
  Screen,
  SectionTitle,
} from '@/components/screens';
import { colors } from '@/components/theme';
import { formatInstant } from '@/lib/dates';
import { formatCents } from '@/lib/formatCents';

import { currentBalance, useBalanceSnapshots, useRecordBalance } from './api';
import { BalanceForm } from './BalanceForm';

export function BalanceScreen() {
  const snapshots = useBalanceSnapshots();
  const record = useRecordBalance();
  // Remounting the form after a save clears what was typed.
  const [formKey, setFormKey] = useState(0);

  if (snapshots.isPending) {
    return <LoadingState />;
  }
  if (snapshots.isError) {
    return (
      <Screen>
        <ErrorState
          error={snapshots.error}
          isRetrying={snapshots.isFetching}
          onRetry={() => snapshots.refetch()}
        />
      </Screen>
    );
  }
  const current = currentBalance(snapshots.data);

  return (
    <Screen>
      {current ? (
        <>
          <Text style={styles.amount}>{formatCents(current.amount_cents)}</Text>
          <Text style={styles.asOf}>As of {formatInstant(current.as_of)}</Text>
        </>
      ) : (
        <EmptyState title="No balance yet" message="Until you add one, your plan starts from $0." />
      )}

      <SectionTitle>Update your balance</SectionTitle>
      <BalanceForm
        key={formKey}
        submitLabel="Save balance"
        isPending={record.isPending}
        error={record.error}
        onSubmit={(cents) => record.mutate(cents, { onSuccess: () => setFormKey((k) => k + 1) })}
      />
      <Paragraph>Each update is kept. The newest one is your current balance.</Paragraph>

      {snapshots.data.length > 1 ? (
        <>
          <SectionTitle>Earlier</SectionTitle>
          {snapshots.data.slice(1).map((snapshot) => (
            <ListRow
              key={snapshot.id}
              title={formatCents(snapshot.amount_cents)}
              subtitle={formatInstant(snapshot.as_of)}
            />
          ))}
        </>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  amount: { color: colors.text, fontSize: 34, fontVariant: ['tabular-nums'], fontWeight: '700' },
  asOf: { color: colors.muted, fontSize: 15 },
});
