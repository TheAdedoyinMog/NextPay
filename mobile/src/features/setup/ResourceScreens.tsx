/**
 * The parts every setup list and edit screen share: loading, error, empty, not found, and
 * removing. Each resource still writes its own form, rows and hooks.
 */
import type { UseMutationResult, UseQueryResult } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import type { ReactNode } from 'react';

import { ActionButton, confirmDelete, FormError, formErrors } from '@/components/form';
import { EmptyState, ErrorState, LoadingState, Screen } from '@/components/screens';

type ListProps<T> = {
  query: UseQueryResult<T[]>;
  empty: { title: string; message: string };
  addLabel: string;
  onAdd: () => void;
  renderItem: (item: T) => ReactNode;
};

export function ResourceList<T>({ query, empty, addLabel, onAdd, renderItem }: ListProps<T>) {
  return (
    <Screen>
      {query.isPending ? <LoadingState /> : null}
      {query.isError ? (
        <ErrorState
          error={query.error}
          isRetrying={query.isFetching}
          onRetry={() => query.refetch()}
        />
      ) : null}
      {query.isSuccess && query.data.length === 0 ? (
        <EmptyState
          title={empty.title}
          message={empty.message}
          actionLabel={addLabel}
          onAction={onAdd}
        />
      ) : null}
      {query.isSuccess && query.data.length > 0 ? (
        <>
          {query.data.map(renderItem)}
          <ActionButton title={addLabel} variant="secondary" onPress={onAdd} />
        </>
      ) : null}
    </Screen>
  );
}

type EditProps<T extends { id: string }> = {
  id: string | undefined;
  query: UseQueryResult<T[]>;
  remove: UseMutationResult<unknown, Error, string>;
  /** "bill", for "This bill is gone". */
  noun: string;
  removeLabel: string;
  confirm: (item: T) => { title: string; message: string; confirmLabel?: string };
  children: (item: T, removeButton: ReactNode) => ReactNode;
};

/**
 * Finds the item in its list (the single source of truth for that resource), and handles
 * every state but the form itself. The form is given the item and the remove button.
 */
export function EditScaffold<T extends { id: string }>({
  id,
  query,
  remove,
  noun,
  removeLabel,
  confirm,
  children,
}: EditProps<T>) {
  const router = useRouter();

  if (remove.isPending || remove.isSuccess) {
    // Leaving: don't flash "gone" while the list refreshes without it.
    return <LoadingState label="Removing…" />;
  }
  if (query.isPending) {
    return <LoadingState />;
  }
  if (query.isError) {
    return (
      <Screen>
        <ErrorState
          error={query.error}
          isRetrying={query.isFetching}
          onRetry={() => query.refetch()}
        />
      </Screen>
    );
  }
  const item = query.data.find((candidate) => candidate.id === id);
  if (!item) {
    return (
      <Screen>
        <EmptyState
          title={`This ${noun} is gone`}
          message="It may have been removed on another device."
          actionLabel="Go back"
          onAction={() => router.back()}
        />
      </Screen>
    );
  }

  const removeButton = (
    <>
      <ActionButton
        title={removeLabel}
        variant="danger"
        onPress={() =>
          confirmDelete({
            ...confirm(item),
            onConfirm: () => remove.mutate(item.id, { onSuccess: () => router.back() }),
          })
        }
      />
      <FormError message={formErrors(remove.error, {}).form} />
    </>
  );
  return <Screen>{children(item, removeButton)}</Screen>;
}
