import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';
import { invalidateAfterSetupChange } from '@/features/setup/invalidate';

export type Bill = components['schemas']['BillResponse'];
export type BillRequest = components['schemas']['BillRequest'];

export const billKeys = {
  all: ['bills'] as const,
};

export function useBills() {
  return useQuery({
    queryKey: billKeys.all,
    queryFn: async () => (await unwrap(api.GET('/bills'))).items,
  });
}

export function useCreateBill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: BillRequest) => unwrap(api.POST('/bills', { body })),
    onSuccess: () => invalidateAfterSetupChange(queryClient, billKeys.all),
  });
}

/** PUT replaces the whole bill; `repeat_every_months` must be sent, as null for a one-off. */
export function useUpdateBill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: BillRequest }) =>
      unwrap(api.PUT('/bills/{bill_id}', { params: { path: { bill_id: id } }, body })),
    onSuccess: () => invalidateAfterSetupChange(queryClient, billKeys.all),
  });
}

/** Deleting a bill also deletes its payment records and releases what was set aside (ADR 0010). */
export function useDeleteBill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE('/bills/{bill_id}', { params: { path: { bill_id: id } } })),
    onSuccess: () => invalidateAfterSetupChange(queryClient, billKeys.all),
  });
}
