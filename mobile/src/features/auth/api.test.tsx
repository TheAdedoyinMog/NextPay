import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';

import { api, unwrap } from '@/api/client';
import { session } from '@/api/session';
import { createFakeBackend, type FakeBackend } from '@/test/fakeBackend';
import * as keychain from '@/test/fakeSecureStore';

import { useSignIn, useSignOut, useSignUp } from './api';
import { SessionProvider, useSession } from './SessionProvider';

jest.mock('@/api/config', () => ({ API_BASE_URL: 'http://api.test' }));
jest.mock('expo-secure-store', () => jest.requireActual('@/test/fakeSecureStore'));

let backend: FakeBackend;
let queryClient: QueryClient;

function wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>{children}</SessionProvider>
    </QueryClientProvider>
  );
}

/** Renders a hook inside the providers, once the session has been restored. */
async function renderAuthHook<T>(hook: () => T) {
  const rendered = await renderHook(() => ({ hook: hook(), session: useSession() }), { wrapper });
  await waitFor(() => expect(rendered.result.current.session.status).not.toBe('restoring'));
  return rendered;
}

beforeEach(() => {
  keychain.reset();
  backend = createFakeBackend();
  backend.addUser('ada@example.com', 'correct horse battery');
  queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { gcTime: Infinity },
    },
  });
});

describe('useSignIn', () => {
  it('starts a session and keeps the refresh token in the Keychain', async () => {
    const { result } = await renderAuthHook(useSignIn);

    await act(() =>
      result.current.hook.mutateAsync({
        email: 'ada@example.com',
        password: 'correct horse battery',
      }),
    );

    expect(result.current.session).toEqual({ status: 'signedIn' });
    expect(keychain.items.get(keychain.REFRESH_TOKEN_KEY)).toMatch(/^refresh-/);
  });

  it('reports wrong credentials in the backend’s words, and stays signed out', async () => {
    const { result } = await renderAuthHook(useSignIn);

    await act(async () => {
      result.current.hook.mutate({ email: 'ada@example.com', password: 'wrong' });
    });

    await waitFor(() => expect(result.current.hook.isError).toBe(true));
    expect(result.current.hook.error).toMatchObject({ message: 'Incorrect email or password.' });
    expect(result.current.session).toEqual({ status: 'signedOut', reason: 'none' });
    expect(keychain.items.size).toBe(0);
  });

  it('reports a network failure', async () => {
    backend.offline = true;
    const { result } = await renderAuthHook(useSignIn);

    await act(async () => {
      result.current.hook.mutate({ email: 'ada@example.com', password: 'whatever' });
    });

    await waitFor(() => expect(result.current.hook.isError).toBe(true));
    expect(result.current.hook.error).toMatchObject({
      code: 'network_error',
      message: 'Could not reach the server at http://api.test.',
    });
  });
});

describe('useSignUp', () => {
  it('creates the account and starts a session', async () => {
    const { result } = await renderAuthHook(useSignUp);

    await act(() =>
      result.current.hook.mutateAsync({ email: 'new@example.com', password: 'a long passphrase' }),
    );

    expect(result.current.session).toEqual({ status: 'signedIn' });
  });

  it('shows the 422 message, which names the field', async () => {
    const { result } = await renderAuthHook(useSignUp);

    await act(async () => {
      result.current.hook.mutate({ email: 'new@example.com', password: 'short' });
    });

    await waitFor(() => expect(result.current.hook.isError).toBe(true));
    expect(result.current.hook.error).toMatchObject({
      status: 422,
      message: 'Check these fields: password',
    });
  });
});

describe('clearing the cache', () => {
  async function signedInWithCachedData() {
    await act(() => session.start(backend.issueSession()));
    queryClient.setQueryData(['me'], { email: 'ada@example.com' });
    queryClient.setQueryData(['bills'], [{ name: 'Rent' }]);
  }

  it('empties the whole query cache on logout', async () => {
    const { result } = await renderAuthHook(useSignOut);
    await signedInWithCachedData();

    await act(() => result.current.hook.mutateAsync());

    expect(result.current.session).toEqual({ status: 'signedOut', reason: 'loggedOut' });
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
    expect(keychain.items.size).toBe(0);
  });

  it('empties it too when the server ends the session', async () => {
    const { result } = await renderAuthHook(() => null);
    await signedInWithCachedData();
    backend.expireAccessTokens();
    backend.refreshFailsWith = 401;

    await act(() =>
      queryClient
        .fetchQuery({ queryKey: ['me', 'again'], queryFn: () => unwrap(api.GET('/me')) })
        .catch(() => null),
    );

    expect(result.current.session).toEqual({ status: 'signedOut', reason: 'ended' });
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
  });
});
