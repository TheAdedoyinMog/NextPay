/**
 * The account's time zone follows the phone's (ADR 0015). The server decides "today" from it:
 * the day a plan is made for, and the default date of a payment. Accounts start in UTC, where
 * 7 PM in Indiana is already tomorrow.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';

import { api, unwrap } from '@/api/client';
import { planningKeys } from '@/features/planning/keys';

import { accountKeys, useMe } from './api';

/** The phone's IANA time zone, such as "America/Indiana/Indianapolis"; null if unknown. */
export function deviceTimeZone(): string | null {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    return null;
  }
}

/** While signed in: if the account's time zone isn't the phone's, change it once. */
export function useTimeZoneSync(): void {
  const queryClient = useQueryClient();
  const me = useMe();
  const sync = useMutation({
    // PUT replaces all settings, so the goal share is sent back unchanged (ADR 0010).
    mutationFn: (body: { timezone: string; no_deadline_goal_share_bps: number }) =>
      unwrap(api.PUT('/me/settings', { body })),
    onSuccess: (user) => {
      queryClient.setQueryData(accountKeys.me, user);
      // A new "today" can change what the dashboard and plans say.
      return queryClient.invalidateQueries({ queryKey: planningKeys.all });
    },
  });

  const wanted = deviceTimeZone();
  const current = me.data?.timezone;
  const share = me.data?.no_deadline_goal_share_bps;
  const { mutate, isIdle } = sync;
  useEffect(() => {
    // Only once per launch: a zone the server rejects must not be retried in a loop.
    if (wanted && current && share !== undefined && current !== wanted && isIdle) {
      mutate({ timezone: wanted, no_deadline_goal_share_bps: share });
    }
  }, [wanted, current, share, isIdle, mutate]);
}
