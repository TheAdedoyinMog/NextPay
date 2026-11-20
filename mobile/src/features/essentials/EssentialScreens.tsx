/** Essential expenses: spending needed every pay period. List, add, edit, delete. */
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
} from '@/components/form';
import { ListRow, Screen } from '@/components/screens';
import { EditScaffold, ResourceList } from '@/features/setup/ResourceScreens';
import { formatCents } from '@/lib/formatCents';
import { centsToText, parseMoney } from '@/lib/money';

import {
  type EssentialRequest,
  useCreateEssential,
  useDeleteEssential,
  useEssentials,
  useUpdateEssential,
} from './api';

type Values = { name: string; amount: string };
type Field = keyof Values;

const FIELD_FOR: Record<string, Field> = { name: 'name', amount_per_period_cents: 'amount' };

type FormProps = {
  initial: Values;
  submitLabel: string;
  isPending: boolean;
  error: unknown;
  onSubmit: (body: EssentialRequest) => void;
  children?: ReactNode;
};

export function EssentialForm({
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
    const amount = parseMoney(values.amount);
    setLocal(amount.ok ? {} : { amount: amount.message });
    if (amount.ok) {
      onSubmit({ name: values.name, amount_per_period_cents: amount.cents });
    }
  };
  return (
    <>
      <TextField
        label="Name"
        value={values.name}
        onChangeText={set('name')}
        placeholder="Groceries"
        autoCapitalize="words"
        error={shown.fields.name}
      />
      <MoneyField
        label="Amount per pay period"
        value={values.amount}
        onChangeText={set('amount')}
        hint="What you need between one paycheck and the next."
        error={shown.fields.amount}
      />
      <FormError message={shown.form} />
      <ActionButton title={submitLabel} isPending={isPending} onPress={submit} />
      {children}
    </>
  );
}

export function EssentialListScreen() {
  const router = useRouter();
  return (
    <ResourceList
      query={useEssentials()}
      empty={{
        title: 'No essentials yet',
        message: 'Add what you spend every pay period, such as groceries and gas.',
      }}
      addLabel="Add essential"
      onAdd={() => router.push('/setup/essentials/new')}
      renderItem={(essential) => (
        <ListRow
          key={essential.id}
          title={essential.name}
          subtitle="Each pay period"
          detail={formatCents(essential.amount_per_period_cents)}
          onPress={() =>
            router.push({ pathname: '/setup/essentials/[id]', params: { id: essential.id } })
          }
        />
      )}
    />
  );
}

export function EssentialNewScreen() {
  const router = useRouter();
  const create = useCreateEssential();
  return (
    <Screen>
      <EssentialForm
        initial={{ name: '', amount: '' }}
        submitLabel="Add essential"
        isPending={create.isPending}
        error={create.error}
        onSubmit={(body) => create.mutate(body, { onSuccess: () => router.back() })}
      />
    </Screen>
  );
}

export function EssentialEditScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const update = useUpdateEssential();
  return (
    <EditScaffold
      id={id}
      query={useEssentials()}
      remove={useDeleteEssential()}
      noun="essential"
      removeLabel="Delete essential"
      confirm={(essential) => ({
        title: `Delete ${essential.name}?`,
        message: 'Plans stop setting money aside for it. Past plans keep its name.',
      })}
    >
      {(essential, removeButton) => (
        <EssentialForm
          initial={{ name: essential.name, amount: centsToText(essential.amount_per_period_cents) }}
          submitLabel="Save changes"
          isPending={update.isPending}
          error={update.error}
          onSubmit={(body) =>
            update.mutate({ id: essential.id, body }, { onSuccess: () => router.back() })
          }
        >
          {removeButton}
        </EssentialForm>
      )}
    </EditScaffold>
  );
}
