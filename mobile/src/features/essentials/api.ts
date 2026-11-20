import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';
import { invalidateAfterSetupChange } from '@/features/setup/invalidate';

export type Essential = components['schemas']['EssentialExpenseResponse'];
export type EssentialRequest = components['schemas']['EssentialExpenseRequest'];

export const essentialKeys = {
  all: ['essential-expenses'] as const,
};

/** Spending needed every pay period, such as groceries and gas. */
export function useEssentials() {
  return useQuery({
    queryKey: essentialKeys.all,
    queryFn: async () => (await unwrap(api.GET('/essential-expenses'))).items,
  });
}

export function useCreateEssential() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: EssentialRequest) => unwrap(api.POST('/essential-expenses', { body })),
    onSuccess: () => invalidateAfterSetupChange(queryClient, essentialKeys.all),
  });
}

export function useUpdateEssential() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: EssentialRequest }) =>
      unwrap(
        api.PUT('/essential-expenses/{essential_expense_id}', {
          params: { path: { essential_expense_id: id } },
          body,
        }),
      ),
    onSuccess: () => invalidateAfterSetupChange(queryClient, essentialKeys.all),
  });
}

export function useDeleteEssential() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.DELETE('/essential-expenses/{essential_expense_id}', {
          params: { path: { essential_expense_id: id } },
        }),
      ),
    onSuccess: () => invalidateAfterSetupChange(queryClient, essentialKeys.all),
  });
}
