/**
 * A fake NextPay API behind `globalThis.fetch`, for tests. Its /auth routes behave like
 * ADR 0009: each refresh rotates the token, and presenting a rotated or revoked token again
 * revokes the whole session. So a client that ever refreshed twice with one token fails here
 * the way it would against the real backend.
 */
import type { components } from '@/api/schema';

type TokenResponse = components['schemas']['TokenResponse'];
type UserResponse = components['schemas']['UserResponse'];

export const BASE_URL = 'http://api.test';

type RefreshTokenState = 'current' | 'rotated' | 'revoked';

interface Family {
  email: string;
  revoked: boolean;
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function error(status: number, code: string, message: string): Response {
  return json(status, { error: { code, message } });
}

export function createFakeBackend() {
  let serial = 0;
  const passwords = new Map<string, string>();
  const families = new Map<number, Family>();
  const refreshTokens = new Map<string, { family: number; state: RefreshTokenState }>();
  const accessTokens = new Map<string, { family: number; expired: boolean }>();
  let refreshGate: Promise<void> | null = null;
  const heldNext = new Map<string, Promise<void>>();

  const backend = {
    /** Every request as "METHOD /path", in arrival order. */
    calls: [] as string[],
    /** Set when a reused refresh token revoked a session: the bug single-flight prevents. */
    reuseDetected: false,
    /** No response at all, as with no signal. */
    offline: false,
    /** Every request, including the retry after a refresh, gets 401 invalid_token. */
    rejectEveryAccessToken: false,
    /** /auth/refresh answers with this status instead of working. */
    refreshFailsWith: null as number | null,

    addUser(email: string, password: string): void {
      passwords.set(email, password);
    },

    /** Starts a session as /auth/login would, without a request. */
    issueSession(email = 'ada@example.com'): TokenResponse {
      passwords.set(email, passwords.get(email) ?? 'correct horse battery');
      serial += 1;
      families.set(serial, { email, revoked: false });
      return issue(serial);
    },

    /** Every access token issued so far now gets 401 token_expired, as after 15 minutes. */
    expireAccessTokens(): void {
      accessTokens.forEach((token) => (token.expired = true));
    },

    isRevoked(refreshToken: string): boolean {
      const token = refreshTokens.get(refreshToken);
      return token === undefined || (families.get(token.family)?.revoked ?? true);
    },

    /** /auth/refresh waits until the returned function is called. */
    holdRefreshes(): () => void {
      let release!: () => void;
      refreshGate = new Promise((resolve) => (release = resolve));
      return () => {
        refreshGate = null;
        release();
      };
    },

    /** Only the next request matching `call` (such as "GET /me") waits until released. */
    holdNext(call: string): () => void {
      let release!: () => void;
      heldNext.set(call, new Promise((resolve) => (release = resolve)));
      return () => release();
    },

    count(call: string): number {
      return backend.calls.filter((c) => c === call).length;
    },

    /** Honors the client's abort signal, so a request that never answers can time out. */
    fetch: jest.fn((request: Request, init?: RequestInit): Promise<Response> => {
      const aborted = new Promise<never>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new Error('Aborted')));
      });
      return Promise.race([handle(request), aborted]);
    }),
  };

  async function handle(request: Request): Promise<Response> {
    if (backend.offline) {
      throw new TypeError('Network request failed');
    }
    const path = request.url.slice(BASE_URL.length);
    const call = `${request.method} ${path}`;
    backend.calls.push(call);
    const body = request.method === 'POST' ? await request.json() : undefined;
    const held = heldNext.get(call);
    if (held) {
      heldNext.delete(call);
      await held;
    }

    switch (call) {
      case 'POST /auth/register':
        return register(body);
      case 'POST /auth/login':
        return login(body);
      case 'POST /auth/refresh':
        if (refreshGate) {
          await refreshGate;
        }
        return refresh(body.refresh_token);
      case 'POST /auth/logout':
        return logout(body.refresh_token);
      case 'GET /me':
        return me(request.headers.get('Authorization'));
      case 'GET /health':
        return json(200, { status: 'ok', engine_version: '1.2.3' });
      default:
        return error(404, 'not_found', 'Not found.');
    }
  }

  function issue(family: number): TokenResponse {
    serial += 1;
    const access = `access-${serial}`;
    const refresh = `refresh-${serial}`;
    accessTokens.set(access, { family, expired: false });
    refreshTokens.set(refresh, { family, state: 'current' });
    return { access_token: access, token_type: 'bearer', expires_in: 900, refresh_token: refresh };
  }

  function register(body: { email: string; password: string }): Response {
    if (body.password.length < 12) {
      return error(422, 'validation_error', 'Check these fields: password');
    }
    if (passwords.has(body.email)) {
      return error(409, 'email_unavailable', "This email can't be used to create an account.");
    }
    backend.addUser(body.email, body.password);
    return json(201, backend.issueSession(body.email));
  }

  function login(body: { email: string; password: string }): Response {
    if (passwords.get(body.email) !== body.password) {
      return error(401, 'invalid_credentials', 'Incorrect email or password.');
    }
    return json(200, backend.issueSession(body.email));
  }

  function revokeFamily(family: number): void {
    const record = families.get(family);
    if (record) {
      record.revoked = true;
    }
    refreshTokens.forEach((token) => {
      if (token.family === family) {
        token.state = 'revoked';
      }
    });
  }

  function refresh(raw: string): Response {
    const ended = () =>
      error(401, 'invalid_refresh_token', 'Your session has ended. Sign in again.');
    if (backend.refreshFailsWith !== null) {
      return backend.refreshFailsWith === 401
        ? ended()
        : error(backend.refreshFailsWith, 'error', 'Something went wrong.');
    }
    const token = refreshTokens.get(raw);
    if (!token) {
      return ended();
    }
    if (token.state !== 'current') {
      backend.reuseDetected = true;
      revokeFamily(token.family);
      return ended();
    }
    token.state = 'rotated';
    return json(200, issue(token.family));
  }

  function logout(raw: string): Response {
    const token = refreshTokens.get(raw);
    if (token) {
      revokeFamily(token.family);
    }
    return new Response(null, { status: 204 });
  }

  function me(authorization: string | null): Response {
    const raw = authorization?.replace(/^Bearer /, '');
    if (!raw) {
      return error(401, 'not_authenticated', 'Sign in to continue.');
    }
    const token = accessTokens.get(raw);
    if (!token || backend.rejectEveryAccessToken) {
      return error(401, 'invalid_token', 'The access token is not valid.');
    }
    if (token.expired) {
      return error(401, 'token_expired', 'The access token has expired.');
    }
    const user: UserResponse = {
      id: `user-${token.family}`,
      email: families.get(token.family)?.email ?? '',
      timezone: 'UTC',
      no_deadline_goal_share_bps: 5000,
      created_at: '2026-11-01T00:00:00Z',
    };
    return json(200, user);
  }

  globalThis.fetch = backend.fetch as unknown as typeof globalThis.fetch;
  return backend;
}

export type FakeBackend = ReturnType<typeof createFakeBackend>;
