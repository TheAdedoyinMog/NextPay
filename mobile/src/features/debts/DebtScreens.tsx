/** Debts: balance, interest rate and minimum payment. List, add, edit, delete. */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { type ReactNode, useState } from 'react';

import {
  ActionButton,
  FormError,
  formErrors,
  mergeErrors,
  MoneyField,
  TextField,
  useFormValues,
  WholeNumberField,
} from '@/components/form';
import { ListRow, Screen } from '@/components/screens';
import { EditScaffold, ResourceList } from '@/features/setup/ResourceScreens';
import { formatCents } from '@/lib/formatCents';
import {
  centsToText,
  hundredthsToText,
  parseHundredths,
  parseMoney,
  parseWholeNumber,
} from '@/lib/money';

import {
  type Debt,
  type DebtRequest,
  useCreateDebt,
  useDebts,
  useDeleteDebt,
  useUpdateDebt,
} from './api';
import { describeDebt } from './labels';

export type DebtValues = {
  name: string;
  balance: string;
  apr: string;
  minimum: string;
  dueDay: string;
};
type Field = keyof DebtValues;

const EMPTY_DEBT: DebtValues = { name: '', balance: '', apr: '', minimum: '', dueDay: '' };

const FIELD_FOR: Record<string, Field> = {
  name: 'name',
  balance_cents: 'balance',
  apr_bps: 'apr',
  minimum_payment_cents: 'minimum',
  due_day: 'dueDay',
};

function debtValues(debt: Debt): DebtValues {
  return {
    name: debt.name,
    balance: centsToText(debt.balance_cents),
    // Basis points are hundredths of a percent: 2499 is "24.99".
    apr: hundredthsToText(debt.apr_bps),
    minimum: centsToText(debt.minimum_payment_cents),
    dueDay: String(debt.due_day),
  };
}

type Built =
  { ok: true; body: DebtRequest } | { ok: false; errors: Partial<Record<Field, string>> };

/** An APR typed as a percent ("24.99") is basis points (2499): the same digits, as text. */
export function parseAprBps(text: string): number | null {
  const bps = parseHundredths(text);
  return bps !== null && bps >= 0 ? bps : null;
}

export function buildDebtRequest(values: DebtValues): Built {
  const errors: Partial<Record<Field, string>> = {};
  const balance = parseMoney(values.balance);
  const minimum = parseMoney(values.minimum);
  const apr = parseAprBps(values.apr);
  const dueDay = parseWholeNumber(values.dueDay);
  if (!balance.ok) errors.balance = balance.message;
  if (!minimum.ok) errors.minimum = minimum.message;
  if (apr === null) errors.apr = 'Enter the rate as a percent with up to two decimals, like 24.99.';
  if (dueDay === null) errors.dueDay = 'Enter a day of the month, like 15.';
  if (!balance.ok || !minimum.ok || apr === null || dueDay === null) {
    return { ok: false, errors };
  }
  return {
    ok: true,
    body: {
      name: values.name,
      balance_cents: balance.cents,
      apr_bps: apr,
      minimum_payment_cents: minimum.cents,
      due_day: dueDay,
    },
  };
}

type FormProps = {
  initial: DebtValues;
  submitLabel: string;
  isPending: boolean;
  error: unknown;
  onSubmit: (body: DebtRequest) => void;
  children?: ReactNode;
};

export function DebtForm({
  initial,
  submitLabel,
  isPending,
  error,
  onSubmit,
  children,
}: FormProps) {
  const [values, set] = useFormValues(initial);
  const [local, setLocal] = useState<Partial<Record<Field, string>>>({});
  const shown = mergeErrors(local, formErrors(error, FIELD_FOR));
  const submit = () => {
    const built = buildDebtRequest(values);
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
        placeholder="Visa card"
        autoCapitalize="words"
        error={shown.fields.name}
      />
      <MoneyField
        label="Balance owed"
        value={values.balance}
        onChangeText={set('balance')}
        error={shown.fields.balance}
      />
      <TextField
        label="Interest rate (APR)"
        value={values.apr}
        onChangeText={set('apr')}
        keyboardType="decimal-pad"
        placeholder="24.99"
        hint="As a percent. 0 if it has no interest."
        error={shown.fields.apr}
      />
      <MoneyField
        label="Minimum payment"
        value={values.minimum}
        onChangeText={set('minimum')}
        hint="Per month."
        error={shown.fields.minimum}
      />
      <WholeNumberField
        label="Due day of the month"
        value={values.dueDay}
        onChangeText={set('dueDay')}
        placeholder="15"
        error={shown.fields.dueDay}
      />
      <FormError message={shown.form} />
      <ActionButton title={submitLabel} isPending={isPending} onPress={submit} />
      {children}
    </>
  );
}

export function DebtListScreen() {
  const router = useRouter();
  return (
    <ResourceList
      query={useDebts()}
      empty={{
        title: 'No debts yet',
        message: 'Add credit cards and loans to plan their payments.',
      }}
      addLabel="Add debt"
      onAdd={() => router.push('/setup/debts/new')}
      renderItem={(debt) => (
        <ListRow
          key={debt.id}
          title={debt.name}
          subtitle={describeDebt(debt)}
          detail={formatCents(debt.balance_cents)}
          onPress={() => router.push({ pathname: '/setup/debts/[id]', params: { id: debt.id } })}
        />
      )}
    />
  );
}

export function DebtNewScreen() {
  const router = useRouter();
  const create = useCreateDebt();
  return (
    <Screen>
      <DebtForm
        initial={EMPTY_DEBT}
        submitLabel="Add debt"
        isPending={create.isPending}
        error={create.error}
        onSubmit={(body) => create.mutate(body, { onSuccess: () => router.back() })}
      />
    </Screen>
  );
}

export function DebtEditScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const update = useUpdateDebt();
  return (
    <EditScaffold
      id={id}
      query={useDebts()}
      remove={useDeleteDebt()}
      noun="debt"
      removeLabel="Delete debt"
      confirm={(debt) => ({
        title: `Delete ${debt.name}?`,
        message:
          'Its payment history is deleted too, and anything set aside for it becomes spendable. Past plans keep its name.',
      })}
    >
      {(debt, removeButton) => (
        <DebtForm
          initial={debtValues(debt)}
          submitLabel="Save changes"
          isPending={update.isPending}
          error={update.error}
          onSubmit={(body) =>
            update.mutate({ id: debt.id, body }, { onSuccess: () => router.back() })
          }
        >
          {removeButton}
        </DebtForm>
      )}
    </EditScaffold>
  );
}
