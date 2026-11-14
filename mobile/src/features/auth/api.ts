import { useMutation } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';
import { session } from '@/api/session';

export type Credentials = components['schemas']['LoginRequest'];

/** Logs in. On success the session starts, and the route guard shows the app. */
export function useSignIn() {
  return useMutation({
    mutationFn: async (credentials: Credentials) =>
      session.start(await unwrap(api.POST('/auth/login', { body: credentials }))),
  });
}

/** Creates an account and signs in. A 422 or 409 message comes from the backend. */
export function useSignUp() {
  return useMutation({
    mutationFn: async (credentials: Credentials) =>
      session.start(await unwrap(api.POST('/auth/register', { body: credentials }))),
  });
}

/** Logs out this device. Never fails: local state is cleared even offline. */
export function useSignOut() {
  return useMutation({ mutationFn: () => session.signOut() });
}
