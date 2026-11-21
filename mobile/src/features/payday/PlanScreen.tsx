/**
 * One paycheck's plan: Safe to Spend, the lines with the engine's explanations, goal
 * projections, and committing it. Every number and sentence is the API's (ADR 0003).
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { ActionButton, confirmDelete, FormError, formErrors } from '@/components/form';
import { ErrorState, LoadingState, Paragraph, Screen, SectionTitle } from '@/components/screens';
import { colors, spacing } from '@/components/theme';
import { ApiError } from '@/api/client';
import { formatCalendarDate, formatInstant } from '@/lib/dates';
import { formatCents } from '@/lib/formatCents';

import { type Plan, type PaycheckKey, useCommitPlan, useGeneratePlan, usePlan } from './api';
import { PlanLines } from './PlanLines';

/** Commit refusals that mean "make the plan again", per ADR 0011's contract. */
const REPLAN_CODES = new Set(['plan_out_of_date', 'plan_superseded']);

export function PlanScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ id: string; updated?: string }>();
  const plan = usePlan(params.id);
  const commit = useCommitPlan();
  const generate = useGeneratePlan();

  if (plan.isPending) {
    return <LoadingState />;
  }
  if (plan.isError) {
    return (
      <Screen>
        <ErrorState
          error={plan.error}
          isRetrying={plan.isFetching}
          onRetry={() => plan.refetch()}
        />
      </Screen>
    );
  }
  const data = plan.data;
  const key: PaycheckKey = {
    incomeSourceId: data.paycheck.income_source_id,
    payDate: data.paycheck.pay_date,
  };
  const replan = () =>
    generate.mutate(key, {
      onSuccess: (next) =>
        router.replace({ pathname: '/plan/[id]', params: { id: next.id, updated: '1' } }),
    });
  const doCommit = () =>
    commit.mutate(data.id, {
      onError: (error) => {
        if (error instanceof ApiError && REPLAN_CODES.has(error.code)) {
          replan(); // not a failure: the details changed, so show the plan they give now
        }
      },
    });
  const askToCommit = () =>
    confirmDelete({
      title: 'Commit this plan?',
      message:
        'What it puts toward bills, debts and goals is set aside, so it no longer counts as safe to spend. Goals grow by their share. A committed plan can’t be changed.',
      confirmLabel: 'Commit',
      onConfirm: doCommit,
    });
  const isDraft = data.status === 'draft';
  const commitError =
    commit.error instanceof ApiError && REPLAN_CODES.has(commit.error.code) ? null : commit.error;

  return (
    <Screen>
      <Text style={styles.muted}>
        {data.paycheck.income_source_name} · {formatCalendarDate(data.paycheck.pay_date)} ·{' '}
        {formatCents(data.paycheck_amount_cents)}
      </Text>

      {params.updated ? (
        <Text accessibilityRole="alert" style={styles.notice}>
          Your details changed, so the plan was updated. Review it, then commit.
        </Text>
      ) : null}
      {isDraft && data.is_out_of_date ? (
        <View style={styles.notice}>
          <Text style={styles.noticeText}>
            Your details changed since this plan was made. Update it before committing.
          </Text>
          <ActionButton
            title="Update the plan"
            isPending={generate.isPending}
            pendingTitle="Updating…"
            onPress={replan}
          />
          <FormError message={formErrors(generate.error, {}).form} />
        </View>
      ) : null}

      <SafeToSpend plan={data} />
      <BalanceUsed plan={data} />
      <Paragraph>{data.summary}</Paragraph>

      <PlanLines plan={data} />

      {data.goal_projections.length > 0 ? (
        <>
          <SectionTitle>Goal outlook</SectionTitle>
          {data.goal_projections.map((projection, index) => (
            <Text key={projection.goal_id ?? index} style={styles.projection}>
              {projection.explanation}
            </Text>
          ))}
        </>
      ) : null}

      {isDraft && !data.is_out_of_date ? (
        <>
          <FormError message={formErrors(commitError, {}).form} />
          <ActionButton
            title="Commit plan"
            pendingTitle="Committing…"
            isPending={commit.isPending || generate.isPending}
            onPress={commit.isError ? doCommit : askToCommit}
          />
        </>
      ) : null}
      {data.status === 'committed' && data.committed_at ? (
        <Text style={styles.committed}>Committed {formatInstant(data.committed_at)}.</Text>
      ) : null}
    </Screen>
  );
}

function SafeToSpend({ plan }: { plan: Plan }) {
  return (
    <View style={styles.card}>
      <Text style={styles.cardLabel}>
        {plan.status === 'draft'
          ? 'Safe to Spend after you commit'
          : 'Safe to Spend when committed'}
      </Text>
      <Text style={styles.big}>{formatCents(plan.safe_to_spend_cents)}</Text>
      {plan.status === 'committed' ? (
        <Text style={styles.muted}>Home shows it now, after what you’ve paid since.</Text>
      ) : null}
      {plan.reserve_deficit_cents > 0 ? (
        <Text accessibilityRole="alert" style={styles.warning}>
          Shortfall: {formatCents(plan.reserve_deficit_cents)}. More is set aside than you have, so
          nothing new could be funded.
        </Text>
      ) : null}
    </View>
  );
}

function BalanceUsed({ plan }: { plan: Plan }) {
  return (
    <Text style={styles.muted}>
      {plan.balance_as_of
        ? `Starts from your balance of ${formatCents(plan.available_balance_cents)}, entered ${formatInstant(plan.balance_as_of)}.`
        : 'No balance was entered, so this plan starts from $0.'}
    </Text>
  );
}

const styles = StyleSheet.create({
  muted: { color: colors.muted, fontSize: 15, marginTop: spacing.xs },
  notice: {
    backgroundColor: colors.noticeBackground,
    borderRadius: 8,
    color: colors.noticeText,
    gap: spacing.xs,
    marginTop: spacing.m,
    padding: spacing.m,
  },
  noticeText: { color: colors.noticeText, fontSize: 15 },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    gap: spacing.xs,
    marginTop: spacing.m,
    padding: spacing.l,
  },
  cardLabel: { color: colors.muted, fontSize: 13, fontWeight: '600', textTransform: 'uppercase' },
  big: { color: colors.text, fontSize: 34, fontVariant: ['tabular-nums'], fontWeight: '700' },
  warning: { color: colors.error, fontSize: 15 },
  projection: { color: colors.label, fontSize: 15, lineHeight: 21, marginTop: spacing.s },
  committed: { color: colors.muted, fontSize: 15, marginTop: spacing.l },
});
