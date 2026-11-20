import type { QueryClient, QueryKey } from '@tanstack/react-query';

import { planningKeys } from '@/features/planning/keys';

/**
 * After any create, update or delete in setup: refetch that resource's list (every screen
 * that shows it, including Home, reads that one query), and mark every planning query stale,
 * because the backend has just made draft plans out of date.
 *
 * Returned from a mutation's `onSuccess`, so the mutation stays pending until the list is
 * fresh: a screen that navigates back on success lands on up-to-date data.
 */
export function invalidateAfterSetupChange(
  queryClient: QueryClient,
  resourceKey: QueryKey,
): Promise<unknown> {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: resourceKey }),
    queryClient.invalidateQueries({ queryKey: planningKeys.all }),
  ]);
}
