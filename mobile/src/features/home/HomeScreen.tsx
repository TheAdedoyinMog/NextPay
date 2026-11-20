/**
 * What's set up, at a glance. 3D puts the next paycheck's plan above this. Nothing here adds
 * anything up: every amount is shown as the API stored it (ADR 0012).
 */
import type { UseQueryResult } from '@tanstack/react-query';
import { type Href, useRouter } from 'expo-router';
import type { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { ActionButton } from '@/components/form';
import { ErrorState, ListRow, LoadingState, Screen } from '@/components/screens';
import { colors, spacing } from '@/components/theme';
import { currentBalance, useBalanceSnapshots } from '@/features/balance/api';
import { useBills } from '@/features/bills/api';
import { describeBill } from '@/features/bills/labels';
import { useDebts } from '@/features/debts/api';
import { describeDebt } from '@/features/debts/labels';
import { useEssentials } from '@/features/essentials/api';
import { useGoals } from '@/features/goals/api';
import { describeGoal } from '@/features/goals/labels';
import { useIncomeSources } from '@/features/income/api';
import { describeSchedule } from '@/features/income/schedule';
import { formatInstant } from '@/lib/dates';
import { formatCents } from '@/lib/formatCents';

export function HomeScreen() {
  const router = useRouter();
  const income = useIncomeSources();
  const bills = useBills();
  const essentials = useEssentials();
  const debts = useDebts();
  const goals = useGoals();

  return (
    <Screen>
      <BalanceCard />

      <Section title="Income" query={income} href="/setup/income" noun="income">
        {(items) =>
          items.map((source) => (
            <ListRow
              key={source.id}
              title={source.name}
              subtitle={describeSchedule(source.schedule)}
              detail={formatCents(source.expected_amount_cents)}
            />
          ))
        }
      </Section>
      <Section title="Bills" query={bills} href="/setup/bills" noun="bills">
        {(items) =>
          items.map((bill) => (
            <ListRow
              key={bill.id}
              title={bill.name}
              subtitle={describeBill(bill)}
              detail={formatCents(bill.amount_cents)}
            />
          ))
        }
      </Section>
      <Section title="Essentials" query={essentials} href="/setup/essentials" noun="essentials">
        {(items) =>
          items.map((essential) => (
            <ListRow
              key={essential.id}
              title={essential.name}
              subtitle="Each pay period"
              detail={formatCents(essential.amount_per_period_cents)}
            />
          ))
        }
      </Section>
      <Section title="Debts" query={debts} href="/setup/debts" noun="debts">
        {(items) =>
          items.map((debt) => (
            <ListRow
              key={debt.id}
              title={debt.name}
              subtitle={describeDebt(debt)}
              detail={formatCents(debt.balance_cents)}
            />
          ))
        }
      </Section>
      <Section title="Goals" query={goals} href="/setup/goals" noun="goals">
        {(items) =>
          items.map((goal) => (
            <ListRow
              key={goal.id}
              title={goal.name}
              subtitle={describeGoal(goal)}
              detail={formatCents(goal.target_cents)}
            />
          ))
        }
      </Section>
      <ActionButton
        title="Change your setup"
        variant="secondary"
        onPress={() => router.push('/setup')}
      />
    </Screen>
  );
}

function BalanceCard() {
  const router = useRouter();
  const snapshots = useBalanceSnapshots();
  const openBalance = () => router.push('/setup/balance');

  return (
    <View style={styles.card}>
      <Text style={styles.cardLabel}>Available balance</Text>
      {snapshots.isPending ? <LoadingState /> : null}
      {snapshots.isError ? (
        <ErrorState
          error={snapshots.error}
          isRetrying={snapshots.isFetching}
          onRetry={() => snapshots.refetch()}
        />
      ) : null}
      {snapshots.isSuccess ? (
        <BalanceValue snapshot={currentBalance(snapshots.data)} onAdd={openBalance} />
      ) : null}
    </View>
  );
}

function BalanceValue({
  snapshot,
  onAdd,
}: {
  snapshot: ReturnType<typeof currentBalance>;
  onAdd: () => void;
}) {
  if (!snapshot) {
    return (
      <>
        <Text style={styles.cardHint}>
          No balance yet. Your plan starts from $0 until you add one.
        </Text>
        <ActionButton title="Add your balance" onPress={onAdd} />
      </>
    );
  }
  return (
    <Pressable accessibilityRole="button" accessibilityLabel="Update balance" onPress={onAdd}>
      <Text style={styles.balance}>{formatCents(snapshot.amount_cents)}</Text>
      <Text style={styles.cardHint}>As of {formatInstant(snapshot.as_of)} · Tap to update</Text>
    </Pressable>
  );
}

type SectionProps<T> = {
  title: string;
  query: UseQueryResult<T[]>;
  href: Href;
  /** For the empty line: "No bills yet". */
  noun: string;
  children: (items: T[]) => ReactNode;
};

function Section<T>({ title, query, href, noun, children }: SectionProps<T>) {
  const router = useRouter();
  return (
    <View style={styles.section}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Manage ${title.toLowerCase()}`}
        onPress={() => router.push(href)}
        style={styles.sectionHeader}
      >
        <Text style={styles.sectionTitle}>{title}</Text>
        <Text style={styles.manage}>Manage ›</Text>
      </Pressable>
      {query.isPending ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState
          error={query.error}
          isRetrying={query.isFetching}
          onRetry={() => query.refetch()}
        />
      ) : null}
      {query.isSuccess && query.data.length === 0 ? (
        <Text style={styles.none}>No {noun} yet.</Text>
      ) : null}
      {query.isSuccess ? children(query.data) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: 12, gap: spacing.xs, padding: spacing.l },
  cardLabel: { color: colors.muted, fontSize: 13, fontWeight: '600', textTransform: 'uppercase' },
  balance: { color: colors.text, fontSize: 34, fontVariant: ['tabular-nums'], fontWeight: '700' },
  cardHint: { color: colors.muted, fontSize: 15 },
  section: { marginTop: spacing.xl },
  sectionHeader: { alignItems: 'baseline', flexDirection: 'row', justifyContent: 'space-between' },
  sectionTitle: { color: colors.text, fontSize: 20, fontWeight: '700' },
  manage: { color: colors.accent, fontSize: 15 },
  none: { color: colors.muted, fontSize: 15, paddingVertical: spacing.s },
});
