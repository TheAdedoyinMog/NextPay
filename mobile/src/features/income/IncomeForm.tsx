/** An income source's fields, for creating one (also in onboarding) and editing one. */
import { type ReactNode, useState } from 'react';

import {
  ActionButton,
  DateField,
  FormError,
  formErrors,
  mergeErrors,
  MoneyField,
  SelectField,
  TextField,
  useFormValues,
  WholeNumberField,
} from '@/components/form';
import { centsToText, parseMoney, parseWholeNumber } from '@/lib/money';

import type { IncomeSource, IncomeSourceRequest, Schedule } from './api';
import { FREQUENCY_OPTIONS, type Frequency } from './schedule';

export type IncomeValues = {
  name: string;
  amount: string;
  frequency: Frequency;
  anchorDate: string | null;
  dayOfMonth: string;
  firstDay: string;
  secondDay: string;
};

type Field = keyof IncomeValues;

export const EMPTY_INCOME: IncomeValues = {
  name: '',
  amount: '',
  frequency: 'biweekly',
  anchorDate: null,
  dayOfMonth: '',
  firstDay: '1',
  secondDay: '15',
};

/** Where the backend's field names land on this form. */
const FIELD_FOR: Record<string, Field> = {
  name: 'name',
  expected_amount_cents: 'amount',
  schedule: 'frequency',
  type: 'frequency',
  anchor_date: 'anchorDate',
  day_of_month: 'dayOfMonth',
  first_day_of_month: 'firstDay',
  second_day_of_month: 'secondDay',
};

export function incomeValues(source: IncomeSource): IncomeValues {
  const { schedule } = source;
  return {
    ...EMPTY_INCOME,
    name: source.name,
    amount: centsToText(source.expected_amount_cents),
    frequency: schedule.type,
    anchorDate: 'anchor_date' in schedule ? schedule.anchor_date : null,
    dayOfMonth: schedule.type === 'monthly' ? String(schedule.day_of_month) : '',
    firstDay: schedule.type === 'semi_monthly' ? String(schedule.first_day_of_month) : '1',
    secondDay: schedule.type === 'semi_monthly' ? String(schedule.second_day_of_month) : '15',
  };
}

type Built =
  { ok: true; body: IncomeSourceRequest } | { ok: false; errors: Partial<Record<Field, string>> };

const DAY_PROBLEM = 'Enter a day of the month, like 15.';

/** The whole request, or what to fix first. Only the format is checked here; rules are the API's. */
export function buildIncomeRequest(values: IncomeValues): Built {
  const errors: Partial<Record<Field, string>> = {};
  const amount = parseMoney(values.amount);
  if (!amount.ok) {
    errors.amount = amount.message;
  }
  let schedule: Schedule | null = null;
  switch (values.frequency) {
    case 'weekly':
    case 'biweekly':
      if (values.anchorDate) {
        schedule = { type: values.frequency, anchor_date: values.anchorDate };
      } else {
        errors.anchorDate = 'Choose a recent or upcoming payday.';
      }
      break;
    case 'monthly': {
      const day = parseWholeNumber(values.dayOfMonth);
      if (day === null) {
        errors.dayOfMonth = DAY_PROBLEM;
      } else {
        schedule = { type: 'monthly', day_of_month: day };
      }
      break;
    }
    case 'semi_monthly': {
      const first = parseWholeNumber(values.firstDay);
      const second = parseWholeNumber(values.secondDay);
      if (first === null) errors.firstDay = DAY_PROBLEM;
      if (second === null) errors.secondDay = DAY_PROBLEM;
      if (first !== null && second !== null) {
        schedule = { type: 'semi_monthly', first_day_of_month: first, second_day_of_month: second };
      }
      break;
    }
  }
  if (!amount.ok || !schedule) {
    return { ok: false, errors };
  }
  return {
    ok: true,
    body: { name: values.name, expected_amount_cents: amount.cents, schedule },
  };
}

type Props = {
  initial: IncomeValues;
  submitLabel: string;
  isPending: boolean;
  /** The last failed save. A 422's problems appear next to their fields. */
  error: unknown;
  onSubmit: (body: IncomeSourceRequest) => void;
  children?: ReactNode;
};

export function IncomeForm({ initial, submitLabel, isPending, error, onSubmit, children }: Props) {
  const [values, set] = useFormValues(initial);
  const [local, setLocal] = useState<Partial<Record<Field, string>>>({});
  const shown = mergeErrors(local, formErrors(error, FIELD_FOR));
  const submit = () => {
    const built = buildIncomeRequest(values);
    setLocal(built.ok ? {} : built.errors);
    if (built.ok) {
      onSubmit(built.body);
    }
  };
  const isWeekly = values.frequency === 'weekly' || values.frequency === 'biweekly';

  return (
    <>
      <TextField
        label="Name"
        value={values.name}
        onChangeText={set('name')}
        placeholder="Acme payroll"
        autoCapitalize="words"
        error={shown.fields.name}
      />
      <MoneyField
        label="Take-home pay per paycheck"
        value={values.amount}
        onChangeText={set('amount')}
        hint="What lands in your account, after taxes."
        error={shown.fields.amount}
      />
      <SelectField
        label="How often you're paid"
        value={values.frequency}
        options={FREQUENCY_OPTIONS}
        onChange={set('frequency')}
        error={shown.fields.frequency}
      />
      {isWeekly ? (
        <DateField
          label="A payday"
          value={values.anchorDate}
          onChange={set('anchorDate')}
          hint="Any recent or upcoming payday. The rest follow from it."
          error={shown.fields.anchorDate}
        />
      ) : null}
      {values.frequency === 'monthly' ? (
        <WholeNumberField
          label="Day of the month"
          value={values.dayOfMonth}
          onChangeText={set('dayOfMonth')}
          placeholder="15"
          hint="Past a month's end, such as the 31st, means its last day."
          error={shown.fields.dayOfMonth}
        />
      ) : null}
      {values.frequency === 'semi_monthly' ? (
        <>
          <WholeNumberField
            label="First payday of the month"
            value={values.firstDay}
            onChangeText={set('firstDay')}
            error={shown.fields.firstDay}
          />
          <WholeNumberField
            label="Second payday of the month"
            value={values.secondDay}
            onChangeText={set('secondDay')}
            hint="At least 7 days apart, such as the 1st and 15th."
            error={shown.fields.secondDay}
          />
        </>
      ) : null}
      <FormError message={shown.form} />
      <ActionButton title={submitLabel} isPending={isPending} onPress={submit} />
      {children}
    </>
  );
}
