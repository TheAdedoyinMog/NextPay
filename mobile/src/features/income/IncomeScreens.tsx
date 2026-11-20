/** Income sources: the list, adding one, and editing or removing one. */
import { useLocalSearchParams, useRouter } from 'expo-router';

import { ListRow, Paragraph, Screen } from '@/components/screens';
import { EditScaffold, ResourceList } from '@/features/setup/ResourceScreens';
import { formatCents } from '@/lib/formatCents';

import {
  useCreateIncomeSource,
  useDeleteIncomeSource,
  useIncomeSources,
  useUpdateIncomeSource,
} from './api';
import { EMPTY_INCOME, IncomeForm, incomeValues } from './IncomeForm';
import { describeSchedule } from './schedule';

export function IncomeListScreen() {
  const router = useRouter();
  return (
    <ResourceList
      query={useIncomeSources()}
      empty={{
        title: 'No income yet',
        message: 'Add your paycheck so NextPay knows when money arrives.',
      }}
      addLabel="Add income"
      onAdd={() => router.push('/setup/income/new')}
      renderItem={(source) => (
        <ListRow
          key={source.id}
          title={source.name}
          subtitle={describeSchedule(source.schedule)}
          detail={formatCents(source.expected_amount_cents)}
          onPress={() => router.push({ pathname: '/setup/income/[id]', params: { id: source.id } })}
        />
      )}
    />
  );
}

export function IncomeNewScreen() {
  const router = useRouter();
  const create = useCreateIncomeSource();
  return (
    <Screen>
      <IncomeForm
        initial={EMPTY_INCOME}
        submitLabel="Add income"
        isPending={create.isPending}
        error={create.error}
        onSubmit={(body) => create.mutate(body, { onSuccess: () => router.back() })}
      />
    </Screen>
  );
}

export function IncomeEditScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const update = useUpdateIncomeSource();
  return (
    <EditScaffold
      id={id}
      query={useIncomeSources()}
      remove={useDeleteIncomeSource()}
      noun="income source"
      removeLabel="Remove income source"
      confirm={(source) => ({
        title: `Remove ${source.name}?`,
        message:
          'It stops counting as income. Any paychecks already recorded stay in your history.',
        confirmLabel: 'Remove',
      })}
    >
      {(source, removeButton) => (
        <IncomeForm
          initial={incomeValues(source)}
          submitLabel="Save changes"
          isPending={update.isPending}
          error={update.error}
          onSubmit={(body) =>
            update.mutate({ id: source.id, body }, { onSuccess: () => router.back() })
          }
        >
          {removeButton}
          <Paragraph>
            Changes apply to future paychecks. Ones already recorded keep their amounts.
          </Paragraph>
        </IncomeForm>
      )}
    </EditScaffold>
  );
}
