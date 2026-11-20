import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';
import { invalidateAfterSetupChange } from '@/features/setup/invalidate';

export type Debt = components['schemas']['DebtResponse'];
export type DebtRequest = components['schemas']['DebtRequest'];

export const debtKeys = {
  all: ['debts'] as const,
};

export function useDebts() {
  return useQuery({
    queryKey: debtKeys.all,
    queryFn: async () => (await unwrap(api.GET('/debts'))).items,
  });
}

export function useCreateDebt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: DebtRequest) => unwrap(api.POST('/debts', { body })),
    onSuccess: () => invalidateAfterSetupChange(queryClient, debtKeys.all),
  });
}

export function useUpdateDebt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: DebtRequest }) =>
      unwrap(api.PUT('/debts/{debt_id}', { params: { path: { debt_id: id } }, body })),
    onSuccess: () => invalidateAfterSetupChange(queryClient, debtKeys.all),
  });
}

/** Deleting a debt also deletes its payment records and releases what was set aside. */
export function useDeleteDebt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE('/debts/{debt_id}', { params: { path: { debt_id: id } } })),
    onSuccess: () => invalidateAfterSetupChange(queryClient, debtKeys.all),
  });
}
