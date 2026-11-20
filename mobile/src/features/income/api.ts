import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';
import { invalidateAfterSetupChange } from '@/features/setup/invalidate';

export type IncomeSource = components['schemas']['IncomeSourceResponse'];
export type IncomeSourceRequest = components['schemas']['IncomeSourceRequest'];
export type Schedule = IncomeSourceRequest['schedule'];

export const incomeKeys = {
  all: ['income-sources'] as const,
};

/** The user's income sources. An archived one is never listed (ADR 0011). */
export function useIncomeSources() {
  return useQuery({
    queryKey: incomeKeys.all,
    queryFn: async () => (await unwrap(api.GET('/income-sources'))).items,
  });
}

export function useCreateIncomeSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: IncomeSourceRequest) => unwrap(api.POST('/income-sources', { body })),
    onSuccess: () => invalidateAfterSetupChange(queryClient, incomeKeys.all),
  });
}

/** PUT replaces the whole source, schedule included (ADR 0010). */
export function useUpdateIncomeSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: IncomeSourceRequest }) =>
      unwrap(
        api.PUT('/income-sources/{income_source_id}', {
          params: { path: { income_source_id: id } },
          body,
        }),
      ),
    onSuccess: () => invalidateAfterSetupChange(queryClient, incomeKeys.all),
  });
}

/**
 * Removes a source. The backend deletes it if it never paid, and otherwise archives it: it
 * stops paying, and its paychecks and plans stay as history. Either way it leaves the list.
 */
export function useDeleteIncomeSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.DELETE('/income-sources/{income_source_id}', {
          params: { path: { income_source_id: id } },
        }),
      ),
    onSuccess: () => invalidateAfterSetupChange(queryClient, incomeKeys.all),
  });
}
