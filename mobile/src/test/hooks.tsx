/**
 * Rendering a feature's query hooks against the fake backend, signed in. The test file must
 * also mock `@/api/config` and `expo-secure-store` (jest.mock calls can't live in a helper).
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react-native';
import type { ReactNode } from 'react';

import { session } from '@/api/session';

import { createFakeBackend, type FakeBackend } from './fakeBackend';
import * as keychain from './fakeSecureStore';

export const EMAIL = 'ada@example.com';

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { retry: false, gcTime: Infinity },
    },
  });
}

/** A fresh fake backend with Ada signed in. */
export async function signedInBackend(): Promise<FakeBackend> {
  keychain.reset();
  const backend = createFakeBackend();
  await act(() => session.start(backend.issueSession(EMAIL)));
  return backend;
}

export async function renderWithClient<T>(hook: () => T, queryClient = createTestQueryClient()) {
  function wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  const rendered = await renderHook(hook, { wrapper });
  return { ...rendered, queryClient };
}
