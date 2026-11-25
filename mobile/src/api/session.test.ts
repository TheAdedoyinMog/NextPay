import { api, unwrap } from '@/api/client';
import { session } from '@/api/session';
import { createFakeBackend, type FakeBackend } from '@/test/fakeBackend';
import * as files from '@/test/fakeFileSystem';
import * as keychain from '@/test/fakeSecureStore';

jest.mock('@/api/config', () => ({ API_BASE_URL: 'http://api.test' }));
jest.mock('expo-secure-store', () => jest.requireActual('@/test/fakeSecureStore'));

let backend: FakeBackend;

function getMe() {
  return unwrap(api.GET('/me'));
}

/** As a fresh launch finds it: a refresh token in the Keychain, nothing in memory. */
async function launchSignedIn() {
  const tokens = backend.issueSession();
  keychain.items.set(keychain.REFRESH_TOKEN_KEY, tokens.refresh_token);
  await session.restore();
  return tokens;
}

/** As log-in leaves it: both tokens in hand. */
async function signIn() {
  const tokens = backend.issueSession();
  await session.start(tokens);
  return tokens;
}

/** Waits (on real timers) until the fake server has seen what the test expects. */
async function until(condition: () => boolean) {
  for (let i = 0; i < 100 && !condition(); i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  expect(condition()).toBe(true);
}

beforeEach(async () => {
  keychain.reset();
  files.reset();
  backend = createFakeBackend();
  await session.restore();
});

describe('first launch after installing (ADR 0019)', () => {
  /** iOS deleted the app, which took the Documents directory, but kept the Keychain. */
  function reinstallKeepingKeychain() {
    const tokens = backend.issueSession();
    keychain.items.set(keychain.REFRESH_TOKEN_KEY, tokens.refresh_token);
    files.uninstall();
    keychain.getItemAsync.mockClear();
    keychain.deleteItemAsync.mockClear();
    return tokens;
  }

  it('signs out a session left in the Keychain by a deleted install', async () => {
    reinstallKeepingKeychain();

    await session.restore();

    expect(session.getState()).toEqual({ status: 'signedOut', reason: 'none' });
    expect(keychain.items.has(keychain.REFRESH_TOKEN_KEY)).toBe(false);
    expect(keychain.getItemAsync).not.toHaveBeenCalled(); // never even read the old token
    expect(backend.calls).toEqual([]); // decided offline, like every launch
  });

  it('clears the Keychain before marking the install, so stopping halfway is safe', async () => {
    reinstallKeepingKeychain();
    const order: string[] = [];
    keychain.deleteItemAsync.mockImplementationOnce(async (key: string) => {
      order.push(files.files.has(files.INSTALL_MARKER) ? 'cleared after marking' : 'cleared');
      keychain.items.delete(key);
    });

    await session.restore();

    expect(order).toEqual(['cleared']);
    expect(files.files.has(files.INSTALL_MARKER)).toBe(true);
  });

  it('keeps a session made after the first launch', async () => {
    reinstallKeepingKeychain();
    await session.restore(); // the first launch: marks the install
    const tokens = backend.issueSession();
    await session.start(tokens); // the user signs in again

    await session.restore(); // the next launch

    expect(session.getState()).toEqual({ status: 'signedIn' });
    expect(keychain.items.get(keychain.REFRESH_TOKEN_KEY)).toBe(tokens.refresh_token);
  });

  it('leaves an existing install alone', async () => {
    await launchSignedIn();

    expect(session.getState()).toEqual({ status: 'signedIn' });
    expect(keychain.deleteItemAsync).not.toHaveBeenCalled();
  });

  it('starts signed out, and tries again next launch, when the Keychain cannot be cleared', async () => {
    reinstallKeepingKeychain();
    keychain.deleteItemAsync.mockRejectedValueOnce(new Error('Keychain locked'));

    await session.restore();

    expect(session.getState()).toEqual({ status: 'signedOut', reason: 'none' });
    expect(files.files.has(files.INSTALL_MARKER)).toBe(false); // so the next launch clears

    await session.restore();

    expect(session.getState()).toEqual({ status: 'signedOut', reason: 'none' });
    expect(keychain.items.has(keychain.REFRESH_TOKEN_KEY)).toBe(false);
    expect(files.files.has(files.INSTALL_MARKER)).toBe(true);
  });

  it('starts signed out when the install cannot be marked', async () => {
    reinstallKeepingKeychain();
    files.failures.write = true;

    await session.restore();

    expect(session.getState()).toEqual({ status: 'signedOut', reason: 'none' });
    expect(keychain.items.has(keychain.REFRESH_TOKEN_KEY)).toBe(false);
  });
});

describe('launch', () => {
  it('is signed out with nothing in the Keychain', () => {
    expect(session.getState()).toEqual({ status: 'signedOut', reason: 'none' });
  });

  it('is signed in with a refresh token in the Keychain, without using the network', async () => {
    await launchSignedIn();

    expect(session.getState()).toEqual({ status: 'signedIn' });
    expect(backend.calls).toEqual([]);
  });

  it('refreshes before the first request instead of sending it without a token', async () => {
    await launchSignedIn();

    await expect(getMe()).resolves.toMatchObject({ email: 'ada@example.com' });
    expect(backend.calls).toEqual(['POST /auth/refresh', 'GET /me']);
  });

  it('stays signed in while offline, and recovers when the network returns', async () => {
    await launchSignedIn();
    backend.offline = true;

    await expect(getMe()).rejects.toMatchObject({ status: 0, code: 'network_error' });
    expect(session.getState()).toEqual({ status: 'signedIn' });

    backend.offline = false;
    await expect(getMe()).resolves.toMatchObject({ email: 'ada@example.com' });
  });
});

describe('refresh', () => {
  it('refreshes and retries when the access token has expired', async () => {
    await signIn();
    backend.expireAccessTokens();

    await expect(getMe()).resolves.toMatchObject({ email: 'ada@example.com' });
    expect(backend.calls).toEqual(['GET /me', 'POST /auth/refresh', 'GET /me']);
  });

  it('keeps the rotated refresh token in the Keychain', async () => {
    const first = await signIn();
    backend.expireAccessTokens();

    await getMe();

    const stored = keychain.items.get(keychain.REFRESH_TOKEN_KEY);
    expect(stored).not.toBe(first.refresh_token);
    expect(backend.isRevoked(stored ?? '')).toBe(false);
  });

  it('shares one refresh among concurrent 401s, then retries each request once', async () => {
    await signIn();
    backend.expireAccessTokens();
    const release = backend.holdRefreshes();

    const requests = Promise.all([getMe(), getMe(), getMe()]);
    // All three are rejected, and all three wait on the one refresh in progress.
    await until(() => backend.count('GET /me') === 3 && backend.count('POST /auth/refresh') === 1);
    release();

    await expect(requests).resolves.toHaveLength(3);
    expect(backend.count('POST /auth/refresh')).toBe(1);
    expect(backend.count('GET /me')).toBe(6);
    expect(backend.reuseDetected).toBe(false);
    expect(session.getState()).toEqual({ status: 'signedIn' });
  });

  it('shares one refresh among concurrent first requests after launch', async () => {
    await launchSignedIn();

    await expect(Promise.all([getMe(), getMe(), getMe()])).resolves.toHaveLength(3);

    expect(backend.calls).toEqual(['POST /auth/refresh', 'GET /me', 'GET /me', 'GET /me']);
    expect(backend.reuseDetected).toBe(false);
  });

  it('does not refresh again for a 401 that arrives after another request refreshed', async () => {
    await signIn();
    const releaseSlow = backend.holdNext('GET /me');
    const slow = getMe(); // sent with the first access token; its answer is held
    await until(() => backend.count('GET /me') === 1);
    backend.expireAccessTokens();

    await getMe(); // rejected, refreshes, retried with the new token
    expect(backend.count('POST /auth/refresh')).toBe(1);
    releaseSlow(); // now the slow request gets its 401 for the old token

    await expect(slow).resolves.toMatchObject({ email: 'ada@example.com' });
    expect(backend.count('POST /auth/refresh')).toBe(1);
    expect(backend.reuseDetected).toBe(false);
  });

  it('retries only once, and a 401 after a successful refresh does not sign out', async () => {
    await signIn();
    backend.rejectEveryAccessToken = true;

    await expect(getMe()).rejects.toMatchObject({ status: 401, code: 'invalid_token' });
    expect(backend.calls).toEqual(['GET /me', 'POST /auth/refresh', 'GET /me']);
    expect(session.getState()).toEqual({ status: 'signedIn' });
  });

  it('never refreshes for /auth routes, whose 401 means wrong credentials', async () => {
    await signIn();

    const login = unwrap(
      api.POST('/auth/login', { body: { email: 'ada@example.com', password: 'wrong' } }),
    );

    await expect(login).rejects.toMatchObject({ status: 401, code: 'invalid_credentials' });
    expect(backend.calls).toEqual(['POST /auth/login']);
  });

  it('sends no token and never refreshes when signed out', async () => {
    await expect(getMe()).rejects.toMatchObject({ status: 401, code: 'not_authenticated' });
    expect(backend.calls).toEqual(['GET /me']);
    expect(backend.fetch.mock.calls[0]?.[0].headers.get('Authorization')).toBeNull();
  });
});

describe('when a refresh fails', () => {
  it('signs out when the refresh is rejected, failing every waiting request', async () => {
    await signIn();
    backend.expireAccessTokens();
    backend.refreshFailsWith = 401;

    const results = await Promise.allSettled([getMe(), getMe(), getMe()]);

    expect(results.map((r) => r.status)).toEqual(['rejected', 'rejected', 'rejected']);
    expect(results[0]).toMatchObject({ reason: { status: 401 } });
    expect(backend.count('POST /auth/refresh')).toBe(1);
    expect(session.getState()).toEqual({ status: 'signedOut', reason: 'ended' });
    expect(keychain.items.size).toBe(0);
  });

  it('stays signed in when the server fails during a refresh', async () => {
    const tokens = await signIn();
    backend.expireAccessTokens();
    backend.refreshFailsWith = 503;

    await expect(getMe()).rejects.toMatchObject({ status: 503 });

    expect(session.getState()).toEqual({ status: 'signedIn' });
    expect(keychain.items.get(keychain.REFRESH_TOKEN_KEY)).toBe(tokens.refresh_token);
  });

  it('stays signed in when a refresh times out', async () => {
    const tokens = await signIn();
    backend.expireAccessTokens();
    backend.holdRefreshes(); // never released: the server never answers
    jest.useFakeTimers();
    try {
      const request = getMe();
      const failure = expect(request).rejects.toMatchObject({ status: 0, code: 'timeout' });
      await jest.advanceTimersByTimeAsync(15_000);
      await failure;
    } finally {
      jest.useRealTimers();
    }

    expect(session.getState()).toEqual({ status: 'signedIn' });
    expect(keychain.items.get(keychain.REFRESH_TOKEN_KEY)).toBe(tokens.refresh_token);
  });
});

describe('logout', () => {
  it('clears the tokens locally and revokes the session on the backend', async () => {
    const tokens = await signIn();

    await session.signOut();

    expect(session.getState()).toEqual({ status: 'signedOut', reason: 'loggedOut' });
    expect(keychain.items.size).toBe(0);
    await until(() => backend.isRevoked(tokens.refresh_token));
    await expect(getMe()).rejects.toMatchObject({ code: 'not_authenticated' });
  });

  it('signs out locally even when the backend cannot be reached', async () => {
    await signIn();
    backend.offline = true;

    await session.signOut();

    expect(session.getState()).toEqual({ status: 'signedOut', reason: 'loggedOut' });
    expect(keychain.items.size).toBe(0);
  });

  it('discards a refresh that finishes after logout', async () => {
    await signIn();
    backend.expireAccessTokens();
    const release = backend.holdRefreshes();
    const request = getMe();
    await until(() => backend.count('POST /auth/refresh') === 1);

    await session.signOut();
    release();

    await expect(request).rejects.toMatchObject({ status: 401 });
    expect(session.getState()).toEqual({ status: 'signedOut', reason: 'loggedOut' });
    expect(keychain.items.size).toBe(0);
  });
});
