/** A bill's fields, for creating and editing one. */
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

import type { Bill, BillRequest } from './api';
import { repeatOptions } from './labels';

export type BillValues = {
  name: string;
  amount: string;
  priority: string;
  firstDueDate: string | null;
  repeatEveryMonths: number | null;
};

type Field = keyof BillValues;

export const EMPTY_BILL: BillValues = {
  name: '',
  amount: '',
  priority: '1',
  firstDueDate: null,
  repeatEveryMonths: 1,
};

const FIELD_FOR: Record<string, Field> = {
  name: 'name',
  amount_cents: 'amount',
  priority: 'priority',
  first_due_date: 'firstDueDate',
  repeat_every_months: 'repeatEveryMonths',
};

export function billValues(bill: Bill): BillValues {
  return {
    name: bill.name,
    amount: centsToText(bill.amount_cents),
    priority: String(bill.priority),
    firstDueDate: bill.first_due_date,
    repeatEveryMonths: bill.repeat_every_months,
  };
}

type Built =
  { ok: true; body: BillRequest } | { ok: false; errors: Partial<Record<Field, string>> };

export function buildBillRequest(values: BillValues): Built {
  const errors: Partial<Record<Field, string>> = {};
  const amount = parseMoney(values.amount);
  const priority = parseWholeNumber(values.priority);
  if (!amount.ok) errors.amount = amount.message;
  if (priority === null) errors.priority = 'Enter a whole number. 1 is the most important.';
  if (!values.firstDueDate) errors.firstDueDate = 'Choose when it is next due.';
  if (!amount.ok || priority === null || !values.firstDueDate) {
    return { ok: false, errors };
  }
  return {
    ok: true,
    body: {
      name: values.name,
      amount_cents: amount.cents,
      priority,
      first_due_date: values.firstDueDate,
      // Always sent: null means it is due once (ADR 0010).
      repeat_every_months: values.repeatEveryMonths,
    },
  };
}

type Props = {
  initial: BillValues;
  submitLabel: string;
  isPending: boolean;
  error: unknown;
  onSubmit: (body: BillRequest) => void;
  children?: ReactNode;
};

export function BillForm({ initial, submitLabel, isPending, error, onSubmit, children }: Props) {
  const [values, set] = useFormValues(initial);
  const [local, setLocal] = useState<Partial<Record<Field, string>>>({});
  const shown = mergeErrors(local, formErrors(error, FIELD_FOR));
  const submit = () => {
    const built = buildBillRequest(values);
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
        placeholder="Rent"
        autoCapitalize="words"
        error={shown.fields.name}
      />
      <MoneyField
        label="Amount"
        value={values.amount}
        onChangeText={set('amount')}
        error={shown.fields.amount}
      />
      <DateField
        label="Next due"
        value={values.firstDueDate}
        onChange={set('firstDueDate')}
        hint="The next date it's due. Later ones follow from it."
        error={shown.fields.firstDueDate}
      />
      <SelectField
        label="Repeats"
        value={values.repeatEveryMonths}
        options={repeatOptions(initial.repeatEveryMonths)}
        onChange={set('repeatEveryMonths')}
        error={shown.fields.repeatEveryMonths}
      />
      <WholeNumberField
        label="Priority"
        value={values.priority}
        onChangeText={set('priority')}
        hint="1 is the most important. Higher-priority bills are covered first."
        error={shown.fields.priority}
      />
      <FormError message={shown.form} />
      <ActionButton title={submitLabel} isPending={isPending} onPress={submit} />
      {children}
    </>
  );
}
