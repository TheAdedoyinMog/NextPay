/**
 * The top of Home: Safe to Spend, the paycheck to act on, the next payday, and the balance.
 * Every number is from GET /dashboard; nothing is added up here (ADR 0003, ADR 0015).
 */
import { useRouter } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { ActionButton } from '@/components/form';
import { ErrorState, LoadingState } from '@/components/screens';
import { colors, spacing } from '@/components/theme';
import { formatCalendarDate, formatInstant } from '@/lib/dates';
import { formatCents } from '@/lib/formatCents';

import { type Dashboard, type Paycheck, useDashboard } from './api';

export function DashboardCards() {
  const dashboard = useDashboard();
  if (dashboard.isPending) {
    return <LoadingState />;
  }
  if (dashboard.isError) {
    return (
      <ErrorState
        error={dashboard.error}
        isRetrying={dashboard.isFetching}
        onRetry={() => dashboard.refetch()}
      />
    );
  }
  const { current_paycheck: current, next_paycheck: next } = dashboard.data;
  return (
    <>
      <SafeToSpendCard safe={dashboard.data.safe_to_spend} />
      {/* Before the first payday, the next one is the one to plan. */}
      {current || next ? <PaycheckCard paycheck={(current ?? next) as Paycheck} /> : null}
      {current && next ? (
        <Text style={styles.muted}>
          Next payday: {formatCalendarDate(next.pay_date)} ({next.income_source_name})
        </Text>
      ) : null}
      <BalanceRow balance={dashboard.data.balance} />
    </>
  );
}

function SafeToSpendCard({ safe }: { safe: Dashboard['safe_to_spend'] }) {
  if (!safe) {
    return (
      <View style={styles.card}>
        <Text style={styles.cardLabel}>Safe to Spend</Text>
        <Text style={styles.muted}>
          Commit a plan for your paycheck to see what’s safe to spend.
        </Text>
      </View>
    );
  }
  return (
    <View style={styles.card}>
      <Text style={styles.cardLabel}>Safe to Spend</Text>
      <Text style={styles.big}>{formatCents(safe.safe_to_spend_cents)}</Text>
      <Text style={styles.muted}>
        From your {formatCalendarDate(safe.pay_date)} plan ({safe.income_source_name})
      </Text>
      {safe.paid_beyond_reserves_cents > 0 ? (
        <Text style={styles.muted}>
          Includes {formatCents(safe.paid_beyond_reserves_cents)} you paid beyond what was set
          aside.
        </Text>
      ) : null}
      {safe.reserve_deficit_cents > 0 ? (
        <Text accessibilityRole="alert" style={styles.warning}>
          Shortfall: {formatCents(safe.reserve_deficit_cents)}. More is set aside or paid than you
          have.
        </Text>
      ) : null}
    </View>
  );
}

function PaycheckCard({ paycheck }: { paycheck: Paycheck }) {
  const router = useRouter();
  const plan = paycheck.plan;
  const openPlan = () => plan && router.push({ pathname: '/plan/[id]', params: { id: plan.id } });
  const startPayday = () =>
    router.push({
      pathname: '/payday',
      params: { incomeSourceId: paycheck.income_source_id, payDate: paycheck.pay_date },
    });

  return (
    <View style={styles.card}>
      <Text style={styles.cardLabel}>Payday · {formatCalendarDate(paycheck.pay_date)}</Text>
      <Text style={styles.title}>
        {paycheck.income_source_name} · {formatCents(paycheck.amount_cents)}
      </Text>
      {!plan ? (
        <>
          <Text style={styles.muted}>No plan yet.</Text>
          <ActionButton title="Plan this paycheck" onPress={startPayday} />
        </>
      ) : null}
      {plan?.status === 'draft' ? (
        <>
          {plan.is_out_of_date ? (
            <Text style={styles.warning}>Your details changed since this plan was made.</Text>
          ) : (
            <Text style={styles.muted}>Draft plan, not committed yet.</Text>
          )}
          <ActionButton
            title={plan.is_out_of_date ? 'Update the plan' : 'Review the plan'}
            onPress={plan.is_out_of_date ? startPayday : openPlan}
          />
        </>
      ) : null}
      {plan?.status === 'committed' ? (
        <>
          <Text style={styles.muted}>Plan committed.</Text>
          <ActionButton title="View the plan" variant="secondary" onPress={openPlan} />
        </>
      ) : null}
    </View>
  );
}

function BalanceRow({ balance }: { balance: Dashboard['balance'] }) {
  const router = useRouter();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Update balance"
      onPress={() => router.push('/setup/balance')}
      style={styles.row}
    >
      <Text style={styles.rowLabel}>Balance</Text>
      {balance ? (
        <View style={styles.rowValue}>
          <Text style={styles.title}>{formatCents(balance.amount_cents)}</Text>
          <Text style={styles.muted}>As of {formatInstant(balance.as_of)}</Text>
        </View>
      ) : (
        <Text style={styles.muted}>No balance yet. Plans start from $0 until you add one.</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    gap: spacing.xs,
    marginBottom: spacing.m,
    padding: spacing.l,
  },
  cardLabel: { color: colors.muted, fontSize: 13, fontWeight: '600', textTransform: 'uppercase' },
  big: { color: colors.text, fontSize: 34, fontVariant: ['tabular-nums'], fontWeight: '700' },
  title: { color: colors.text, fontSize: 17, fontWeight: '600' },
  muted: { color: colors.muted, fontSize: 15 },
  warning: { color: colors.error, fontSize: 15 },
  row: { gap: spacing.xs, paddingVertical: spacing.s },
  rowLabel: { color: colors.muted, fontSize: 13, fontWeight: '600', textTransform: 'uppercase' },
  rowValue: { gap: 2 },
});
