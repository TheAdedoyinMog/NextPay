/** A goal's fields, for creating one (also onboarding's emergency fund) and editing one. */
import { type ReactNode, useState } from 'react';

import {
  ActionButton,
  DateField,
  FormError,
  formErrors,
  mergeErrors,
  MoneyField,
  SelectField,
  type SelectOption,
  TextField,
  useFormValues,
  WholeNumberField,
} from '@/components/form';
import { centsToText, parseMoney, parseWholeNumber } from '@/lib/money';

import type { Goal, GoalKind, GoalRequest } from './api';

export type GoalValues = {
  name: string;
  kind: GoalKind;
  target: string;
  saved: string;
  priority: string;
  deadline: string | null;
};

type Field = keyof GoalValues;

export const GOAL_KIND_OPTIONS: readonly SelectOption<GoalKind>[] = [
  { value: 'emergency', label: 'Emergency fund' },
  { value: 'savings', label: 'Savings' },
  { value: 'purchase', label: 'Something to buy' },
];

export const EMPTY_GOAL: GoalValues = {
  name: '',
  kind: 'savings',
  target: '',
  saved: '0.00',
  priority: '1',
  deadline: null,
};

const FIELD_FOR: Record<string, Field> = {
  name: 'name',
  kind: 'kind',
  target_cents: 'target',
  current_cents: 'saved',
  priority: 'priority',
  deadline: 'deadline',
};

export function goalValues(goal: Goal): GoalValues {
  return {
    name: goal.name,
    kind: goal.kind,
    target: centsToText(goal.target_cents),
    saved: centsToText(goal.current_cents),
    priority: String(goal.priority),
    deadline: goal.deadline,
  };
}

type Built =
  { ok: true; body: GoalRequest } | { ok: false; errors: Partial<Record<Field, string>> };

export function buildGoalRequest(values: GoalValues): Built {
  const errors: Partial<Record<Field, string>> = {};
  const target = parseMoney(values.target);
  const saved = parseMoney(values.saved);
  const priority = parseWholeNumber(values.priority);
  if (!target.ok) errors.target = target.message;
  if (!saved.ok) errors.saved = saved.message;
  if (priority === null) errors.priority = 'Enter a whole number. 1 is the most important.';
  if (!target.ok || !saved.ok || priority === null) {
    return { ok: false, errors };
  }
  return {
    ok: true,
    body: {
      name: values.name,
      kind: values.kind,
      target_cents: target.cents,
      current_cents: saved.cents,
      priority,
      // Always sent: null clears the deadline (ADR 0010).
      deadline: values.deadline,
    },
  };
}

type Props = {
  initial: GoalValues;
  submitLabel: string;
  isPending: boolean;
  error: unknown;
  onSubmit: (body: GoalRequest) => void;
  /** Next to the submit button, such as onboarding's Skip. */
  secondaryAction?: ReactNode;
  children?: ReactNode;
};

export function GoalForm({
  initial,
  submitLabel,
  isPending,
  error,
  onSubmit,
  secondaryAction,
  children,
}: Props) {
  const [values, set] = useFormValues(initial);
  const [local, setLocal] = useState<Partial<Record<Field, string>>>({});
  const shown = mergeErrors(local, formErrors(error, FIELD_FOR));
  const submit = () => {
    const built = buildGoalRequest(values);
    setLocal(built.ok ? {} : built.errors);
    if (built.ok) {
      onSubmit(built.body);
    }
  };

  return (
    <>
      <TextField
        label="Name"
        value={values.name}
        onChangeText={set('name')}
        placeholder="New laptop"
        autoCapitalize="sentences"
        error={shown.fields.name}
      />
      <SelectField
        label="Kind"
        value={values.kind}
        options={GOAL_KIND_OPTIONS}
        onChange={set('kind')}
        error={shown.fields.kind}
      />
      <MoneyField
        label="Target"
        value={values.target}
        onChangeText={set('target')}
        error={shown.fields.target}
      />
      <MoneyField
        label="Saved so far"
        value={values.saved}
        onChangeText={set('saved')}
        error={shown.fields.saved}
      />
      <WholeNumberField
        label="Priority"
        value={values.priority}
        onChangeText={set('priority')}
        hint="1 is the most important."
        error={shown.fields.priority}
      />
      <DateField
        label="Deadline"
        value={values.deadline}
        onChange={set('deadline')}
        noneLabel="No deadline"
        error={shown.fields.deadline}
      />
      <FormError message={shown.form} />
      <ActionButton title={submitLabel} isPending={isPending} onPress={submit} />
      {secondaryAction}
      {children}
    </>
  );
}
