import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';

import { api, unwrap } from '@/api/client';
import { session } from '@/api/session';
import * as apple from '@/test/fakeAppleAuthentication';
import { createFakeBackend, type FakeBackend } from '@/test/fakeBackend';
import { sha256Hex } from '@/test/fakeCrypto';
import * as keychain from '@/test/fakeSecureStore';

import { AppleSignInError, useAppleSignIn } from './apple';
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

async function renderAppleSignIn() {
  const rendered = await renderHook(() => ({ hook: useAppleSignIn(), session: useSession() }), {
    wrapper,
  });
  await waitFor(() => expect(rendered.result.current.session.status).not.toBe('restoring'));
  return rendered;
}

type AppleBody = { identity_token: string; nonce: string; full_name: string | null };

function appleBodies(): AppleBody[] {
  return backend.bodies
    .filter((entry) => entry.call === 'POST /auth/apple')
    .map((entry) => entry.body as AppleBody);
}

beforeEach(async () => {
  await session.signOut();
  keychain.reset();
  apple.reset();
  backend = createFakeBackend();
  queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { gcTime: Infinity },
    },
  });
});

describe('useAppleSignIn', () => {
  it('signs in the first time, sending the name Apple shares only then', async () => {
    const { result } = await renderAppleSignIn();

    await act(async () => {
      await expect(result.current.hook.mutateAsync()).resolves.toBe('signedIn');
    });

    expect(result.current.session).toEqual({ status: 'signedIn' });
    expect(keychain.items.get(keychain.REFRESH_TOKEN_KEY)).toMatch(/^refresh-/);
    expect(appleBodies()).toEqual([
      { identity_token: expect.any(String), nonce: expect.any(String), full_name: 'Ada Lovelace' },
    ]);
    await expect(unwrap(api.GET('/me'))).resolves.toMatchObject({
      email: null,
      display_name: 'Ada Lovelace',
    });
  });

  it('gives Apple the hash of a fresh random nonce, and sends the backend the raw one', async () => {
    const { result } = await renderAppleSignIn();

    await act(() => result.current.hook.mutateAsync());
    await act(() => result.current.hook.mutateAsync());

    const given = apple.signInAsync.mock.calls.map(([options]) => options?.nonce);
    const sent = appleBodies().map((body) => body.nonce);
    expect(sent[0]).toMatch(/^[0-9a-f]{64}$/); // 32 random bytes
    expect(sent[0]).not.toBe(sent[1]); // one nonce per attempt
    expect(given).toEqual(sent.map(sha256Hex));
    expect(apple.signInAsync.mock.calls[0]?.[0]).toMatchObject({
      requestedScopes: [
        apple.AppleAuthenticationScope.FULL_NAME,
        apple.AppleAuthenticationScope.EMAIL,
      ],
    });
  });

  it('signs in to the same account later, when Apple no longer shares the name', async () => {
    const { result } = await renderAppleSignIn();
    await act(() => result.current.hook.mutateAsync());
    const first = await unwrap(api.GET('/me'));
    await act(() => session.signOut());

    await act(() => result.current.hook.mutateAsync());

    expect(appleBodies()[1]?.full_name).toBeNull();
    const later = await unwrap(api.GET('/me'));
    expect(later.id).toBe(first.id);
    expect(later.display_name).toBe('Ada Lovelace');
  });

  it('treats closing Apple’s sheet as a choice, not an error', async () => {
    apple.next.outcome = 'cancel';
    const { result } = await renderAppleSignIn();

    await act(async () => {
      await expect(result.current.hook.mutateAsync()).resolves.toBe('canceled');
    });

    expect(result.current.hook.error).toBeNull();
    expect(result.current.session).toEqual({ status: 'signedOut', reason: 'none' });
    expect(backend.calls).toEqual([]);
  });

  it.each(['fail', 'noToken'] as const)(
    'reports Apple failing (%s) without calling the backend',
    async (outcome) => {
      apple.next.outcome = outcome;
      const { result } = await renderAppleSignIn();

      await act(async () => {
        result.current.hook.mutate();
      });

      await waitFor(() => expect(result.current.hook.error).toBeInstanceOf(AppleSignInError));
      expect(result.current.session).toEqual({ status: 'signedOut', reason: 'none' });
      expect(backend.calls).toEqual([]);
    },
  );

  it('reports a rejected token in the backend’s words, and stays signed out', async () => {
    backend.failNext('POST /auth/apple', 401, {
      code: 'invalid_apple_token',
      message: "Sign in with Apple didn't work. Try again.",
    });
    const { result } = await renderAppleSignIn();

    await act(async () => {
      result.current.hook.mutate();
    });

    await waitFor(() => expect(result.current.hook.isError).toBe(true));
    expect(result.current.hook.error).toMatchObject({
      status: 401,
      message: "Sign in with Apple didn't work. Try again.",
    });
    expect(result.current.session).toEqual({ status: 'signedOut', reason: 'none' });
    expect(keychain.items.size).toBe(0);
  });

  it('reports a network failure and stays signed out', async () => {
    backend.offline = true;
    const { result } = await renderAppleSignIn();

    await act(async () => {
      result.current.hook.mutate();
    });

    await waitFor(() => expect(result.current.hook.isError).toBe(true));
    expect(result.current.hook.error).toMatchObject({ code: 'network_error' });
    expect(result.current.session).toEqual({ status: 'signedOut', reason: 'none' });
  });

  it('refreshes an Apple session like any other', async () => {
    const { result } = await renderAppleSignIn();
    await act(() => result.current.hook.mutateAsync());
    backend.expireAccessTokens();

    await expect(unwrap(api.GET('/me'))).resolves.toMatchObject({ email: null });
    expect(backend.calls).toEqual(['POST /auth/apple', 'GET /me', 'POST /auth/refresh', 'GET /me']);
  });
});
