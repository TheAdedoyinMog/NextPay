/** Bills: the list, adding one, and editing or deleting one. */
import { useLocalSearchParams, useRouter } from 'expo-router';

import { ListRow, Screen } from '@/components/screens';
import { EditScaffold, ResourceList } from '@/features/setup/ResourceScreens';
import { formatCents } from '@/lib/formatCents';

import { useBills, useCreateBill, useDeleteBill, useUpdateBill } from './api';
import { BillForm, billValues, EMPTY_BILL } from './BillForm';
import { describeBill } from './labels';

export function BillListScreen() {
  const router = useRouter();
  return (
    <ResourceList
      query={useBills()}
      empty={{
        title: 'No bills yet',
        message: 'Add rent, phone, insurance: anything with a due date.',
      }}
      addLabel="Add bill"
      onAdd={() => router.push('/setup/bills/new')}
      renderItem={(bill) => (
        <ListRow
          key={bill.id}
          title={bill.name}
          subtitle={describeBill(bill)}
          detail={formatCents(bill.amount_cents)}
          onPress={() => router.push({ pathname: '/setup/bills/[id]', params: { id: bill.id } })}
        />
      )}
    />
  );
}

export function BillNewScreen() {
  const router = useRouter();
  const create = useCreateBill();
  return (
    <Screen>
      <BillForm
        initial={EMPTY_BILL}
        submitLabel="Add bill"
        isPending={create.isPending}
        error={create.error}
        onSubmit={(body) => create.mutate(body, { onSuccess: () => router.back() })}
      />
    </Screen>
  );
}

export function BillEditScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const update = useUpdateBill();
  return (
    <EditScaffold
      id={id}
      query={useBills()}
      remove={useDeleteBill()}
      noun="bill"
      removeLabel="Delete bill"
      confirm={(bill) => ({
        title: `Delete ${bill.name}?`,
        message:
          'Its payment history is deleted too, and anything set aside for it becomes spendable. Past plans keep its name.',
      })}
    >
      {(bill, removeButton) => (
        <BillForm
          initial={billValues(bill)}
          submitLabel="Save changes"
          isPending={update.isPending}
          error={update.error}
          onSubmit={(body) =>
            update.mutate({ id: bill.id, body }, { onSuccess: () => router.back() })
          }
        >
          {removeButton}
        </BillForm>
      )}
    </EditScaffold>
  );
}
