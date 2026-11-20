import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';
import { invalidateAfterSetupChange } from '@/features/setup/invalidate';

export type BalanceSnapshot = components['schemas']['BalanceSnapshotResponse'];

/** How many past balances the app shows. */
const HISTORY_LIMIT = 10;

export const balanceKeys = {
  all: ['balance-snapshots'] as const,
};

/**
 * Recent balances, newest first. The newest is the current balance (ADR 0010). Snapshots are
 * append-only: a new balance is a new snapshot, and none can be edited or deleted.
 */
export function useBalanceSnapshots() {
  return useQuery({
    queryKey: balanceKeys.all,
    queryFn: async () =>
      (await unwrap(api.GET('/balance-snapshots', { params: { query: { limit: HISTORY_LIMIT } } })))
        .items,
  });
}

/** The current balance, or null when none has been entered (a plan then starts from $0). */
export function currentBalance(snapshots: readonly BalanceSnapshot[]): BalanceSnapshot | null {
  return snapshots[0] ?? null;
}

export function useRecordBalance() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (amountCents: number) =>
      unwrap(api.POST('/balance-snapshots', { body: { amount_cents: amountCents } })),
    onSuccess: () => invalidateAfterSetupChange(queryClient, balanceKeys.all),
  });
}
