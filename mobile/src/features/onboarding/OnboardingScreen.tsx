/**
 * First run: income and pay schedule, then the current balance, then the suggested emergency
 * fund. Each step saves as it goes, so leaving halfway keeps what was entered.
 *
 * A step that is already done is left out: an account that has a balance, or an emergency
 * goal, skips that step. That happens when a user who removed their only income is onboarded
 * again (ADR 0014), and it keeps them from entering a second emergency goal.
 */
import { useState } from 'react';
import { StyleSheet, Text } from 'react-native';

import { ActionButton } from '@/components/form';
import { LoadingState, Paragraph, Screen } from '@/components/screens';
import { colors, spacing } from '@/components/theme';
import { useSignOut } from '@/features/auth/api';
import { useBalanceSnapshots, useRecordBalance } from '@/features/balance/api';
import { BalanceForm } from '@/features/balance/BalanceForm';
import { useCreateGoal, useGoals } from '@/features/goals/api';
import { GoalForm, type GoalValues } from '@/features/goals/GoalForm';
import { useCreateIncomeSource } from '@/features/income/api';
import { EMPTY_INCOME, IncomeForm } from '@/features/income/IncomeForm';

import { useFinishOnboarding } from './OnboardingGate';

export type Step = 'income' | 'balance' | 'goal';

/**
 * The steps still to do. Income is always one: onboarding only runs without it. A list that
 * failed to load keeps its step, which is safe: the backend still refuses a second emergency
 * goal with a message, and every later step can be skipped.
 */
export function onboardingSteps(
  balance: { isSuccess: boolean; data?: readonly unknown[] },
  goals: { isSuccess: boolean; data?: readonly { kind: string }[] },
): Step[] {
  const steps: Step[] = ['income'];
  if (!(balance.isSuccess && balance.data && balance.data.length > 0)) {
    steps.push('balance');
  }
  if (!(goals.isSuccess && goals.data?.some((goal) => goal.kind === 'emergency'))) {
    steps.push('goal');
  }
  return steps;
}

/**
 * The design's suggested starting emergency fund. A suggestion the user can change or skip,
 * not a calculation: the app only fills in the field.
 */
export const SUGGESTED_EMERGENCY_GOAL: GoalValues = {
  name: 'Emergency fund',
  kind: 'emergency',
  target: '1000.00',
  saved: '0.00',
  priority: '1',
  deadline: null,
};

export function OnboardingScreen() {
  const signOut = useSignOut();
  const finish = useFinishOnboarding();
  const balance = useBalanceSnapshots();
  const goals = useGoals();
  // Planned once, from the first answers, then held: saving the balance refetches it, and
  // recomputing would drop the step being shown and renumber the rest.
  const [steps, setSteps] = useState<Step[] | null>(null);
  const [index, setIndex] = useState(0);
  if (steps === null && !balance.isPending && !goals.isPending) {
    setSteps(onboardingSteps(balance, goals));
  }

  if (steps === null) {
    return <LoadingState />;
  }
  const step = steps[index];
  const next = () => (index + 1 < steps.length ? setIndex(index + 1) : finish());

  return (
    <Screen>
      <Text style={styles.progress}>
        Step {index + 1} of {steps.length}
      </Text>
      {step === 'income' ? <IncomeStep onDone={next} /> : null}
      {step === 'balance' ? <BalanceStep onDone={next} /> : null}
      {step === 'goal' ? <GoalStep onDone={next} /> : null}
      <ActionButton
        title="Log out"
        variant="secondary"
        disabled={signOut.isPending}
        onPress={() => signOut.mutate()}
      />
    </Screen>
  );
}

function IncomeStep({ onDone }: { onDone: () => void }) {
  const create = useCreateIncomeSource();
  return (
    <>
      <Text accessibilityRole="header" style={styles.title}>
        When do you get paid?
      </Text>
      <Paragraph>Start with your main paycheck. You can add more later.</Paragraph>
      <IncomeForm
        initial={EMPTY_INCOME}
        submitLabel="Continue"
        isPending={create.isPending}
        error={create.error}
        onSubmit={(body) => create.mutate(body, { onSuccess: onDone })}
      />
    </>
  );
}

function BalanceStep({ onDone }: { onDone: () => void }) {
  const record = useRecordBalance();
  return (
    <>
      <Text accessibilityRole="header" style={styles.title}>
        How much do you have right now?
      </Text>
      <Paragraph>
        Your plan starts from this. If you skip it, the plan starts from $0 until you add it.
      </Paragraph>
      <BalanceForm
        submitLabel="Continue"
        isPending={record.isPending}
        error={record.error}
        onSubmit={(cents) => record.mutate(cents, { onSuccess: onDone })}
      >
        <ActionButton title="Skip for now" variant="secondary" onPress={onDone} />
      </BalanceForm>
    </>
  );
}

function GoalStep({ onDone }: { onDone: () => void }) {
  const create = useCreateGoal();
  return (
    <>
      <Text accessibilityRole="header" style={styles.title}>
        Start an emergency fund
      </Text>
      <Paragraph>
        A cushion for surprises keeps one bad week from becoming debt. We suggest starting with
        $1,000. Change it to whatever fits, or skip it.
      </Paragraph>
      <GoalForm
        initial={SUGGESTED_EMERGENCY_GOAL}
        submitLabel="Save goal"
        isPending={create.isPending}
        error={create.error}
        onSubmit={(body) => create.mutate(body, { onSuccess: onDone })}
        secondaryAction={<ActionButton title="Skip" variant="secondary" onPress={onDone} />}
      />
    </>
  );
}

const styles = StyleSheet.create({
  progress: { color: colors.muted, fontSize: 14 },
  title: { color: colors.text, fontSize: 26, fontWeight: '700', marginTop: spacing.s },
});
