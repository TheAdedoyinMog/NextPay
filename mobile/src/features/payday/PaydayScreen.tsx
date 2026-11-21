/**
 * Planning a paycheck: what it paid, then the balance before it arrived (asked every time,
 * ADR 0015), then the plan. Each step is safe to repeat (see api.ts).
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text } from 'react-native';

import { ActionButton, FormError, formErrors, mergeErrors, MoneyField } from '@/components/form';
import { EmptyState, ErrorState, LoadingState, Paragraph, Screen } from '@/components/screens';
import { colors, spacing } from '@/components/theme';
import { useRecordBalance } from '@/features/balance/api';
import { BalanceForm } from '@/features/balance/BalanceForm';
import { formatCalendarDate } from '@/lib/dates';
import { formatCents } from '@/lib/formatCents';
import { centsToText, parseMoney } from '@/lib/money';

import {
  type Paycheck,
  type PaycheckKey,
  useDashboard,
  useGeneratePlan,
  useRecordActualAmount,
} from './api';

export function PaydayScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ incomeSourceId: string; payDate: string }>();
  const dashboard = useDashboard();
  const [step, setStep] = useState<'amount' | 'balance'>('amount');
  const recordBalance = useRecordBalance();
  const generate = useGeneratePlan();

  if (dashboard.isPending) {
    return <LoadingState />;
  }
  if (dashboard.isError) {
    return (
      <Screen>
        <ErrorState
          error={dashboard.error}
          isRetrying={dashboard.isFetching}
          onRetry={() => dashboard.refetch()}
        />
      </Screen>
    );
  }
  const paycheck = [dashboard.data.current_paycheck, dashboard.data.next_paycheck].find(
    (candidate) =>
      candidate?.income_source_id === params.incomeSourceId &&
      candidate.pay_date === params.payDate,
  );
  if (!paycheck) {
    return (
      <Screen>
        <EmptyState
          title="This payday isn't current any more"
          message="Go back to Home to plan the paycheck that is."
          actionLabel="Back to Home"
          onAction={() => router.back()}
        />
      </Screen>
    );
  }
  const key: PaycheckKey = {
    incomeSourceId: paycheck.income_source_id,
    payDate: paycheck.pay_date,
  };
  const makePlan = () =>
    generate.mutate(key, {
      onSuccess: (plan) => router.replace({ pathname: '/plan/[id]', params: { id: plan.id } }),
    });
  const balance = dashboard.data.balance;

  return (
    <Screen>
      <Text style={styles.progress}>
        {paycheck.income_source_name} · {formatCalendarDate(paycheck.pay_date)} · Step{' '}
        {step === 'amount' ? 1 : 2} of 2
      </Text>
      {step === 'amount' ? (
        <AmountStep paycheck={paycheck} paycheckKey={key} onDone={() => setStep('balance')} />
      ) : (
        <>
          <Text accessibilityRole="header" style={styles.title}>
            Your balance before this paycheck
          </Text>
          <Paragraph>
            The plan starts from what you had before this paycheck arrived, so don’t include it.
            Check your account and correct this if it has changed.
          </Paragraph>
          <BalanceForm
            label="Balance before this paycheck"
            hint="Use a minus sign if you're overdrawn."
            initialText={balance ? centsToText(balance.amount_cents) : ''}
            submitLabel="Make my plan"
            isPending={recordBalance.isPending || generate.isPending}
            error={recordBalance.error}
            onSubmit={(cents) => recordBalance.mutate(cents, { onSuccess: makePlan })}
          >
            {generate.isError ? (
              <>
                <FormError message={formErrors(generate.error, {}).form} />
                <ActionButton title="Try again" variant="secondary" onPress={makePlan} />
              </>
            ) : null}
          </BalanceForm>
        </>
      )}
    </Screen>
  );
}

function AmountStep({
  paycheck,
  paycheckKey,
  onDone,
}: {
  paycheck: Paycheck;
  paycheckKey: PaycheckKey;
  onDone: () => void;
}) {
  const record = useRecordActualAmount();
  const [text, setText] = useState(centsToText(paycheck.amount_cents));
  const [local, setLocal] = useState<{ amount?: string }>({});
  const shown = mergeErrors(local, formErrors(record.error, { actual_amount_cents: 'amount' }));
  const submit = () => {
    const parsed = parseMoney(text);
    setLocal(parsed.ok ? {} : { amount: parsed.message });
    if (parsed.ok) {
      record.mutate({ paycheck: paycheckKey, cents: parsed.cents }, { onSuccess: onDone });
    }
  };
  return (
    <>
      <Text accessibilityRole="header" style={styles.title}>
        What did this paycheck pay?
      </Text>
      <Paragraph>
        Expected: {formatCents(paycheck.expected_amount_cents)}. Change it if a different amount
        arrived.
      </Paragraph>
      <MoneyField
        label="Amount that arrived"
        value={text}
        onChangeText={setText}
        error={shown.fields.amount}
      />
      <FormError message={shown.form} />
      <ActionButton title="Continue" isPending={record.isPending} onPress={submit} />
    </>
  );
}

const styles = StyleSheet.create({
  progress: { color: colors.muted, fontSize: 14 },
  title: { color: colors.text, fontSize: 24, fontWeight: '700', marginTop: spacing.s },
});
