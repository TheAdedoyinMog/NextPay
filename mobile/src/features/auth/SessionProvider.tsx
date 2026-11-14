import { useQueryClient } from '@tanstack/react-query';
import { type ReactNode, useEffect, useSyncExternalStore } from 'react';

import { session, type SessionState } from '@/api/session';

/** The session as React state: re-renders whenever someone signs in or out. */
export function useSession(): SessionState {
  return useSyncExternalStore(session.subscribe, session.getState);
}

/**
 * Restores the session at launch, and empties the query cache whenever nobody is signed in,
 * whether by logging out or because the server ended the session. The cache is cleared from
 * the session's own notification, before any screen re-renders, so no data from one account
 * is ever shown to the next.
 */
export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  useEffect(
    () =>
      session.subscribe(() => {
        if (session.getState().status === 'signedOut') {
          void queryClient.cancelQueries();
          queryClient.clear(); // queries and mutations
        }
      }),
    [queryClient],
  );

  useEffect(() => {
    void session.restore();
  }, []);

  return children;
}
