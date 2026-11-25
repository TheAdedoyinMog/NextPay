/**
 * A fake NextPay API behind `globalThis.fetch`, for tests. Its /auth routes behave like
 * ADR 0009: each refresh rotates the token, and presenting a rotated or revoked token again
 * revokes the whole session. So a client that ever refreshed twice with one token fails here
 * the way it would against the real backend.
 *
 * The setup resources (income sources, bills, essentials, debts, goals, balance snapshots)
 * are kept in memory per user, in the real API's shape (ADR 0010): PUT needs every field,
 * nullable ones included, and a 422 names each field in `fields`. Only the checks the app's
 * error handling depends on are copied; the backend's own tests cover the rest.
 */
import type { components } from '@/api/schema';

import { sha256Hex } from './fakeCrypto';
import { createFakePlanning } from './fakePlanning';

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

function error(
  status: number,
  code: string,
  message: string,
  fields?: Record<string, string>,
): Response {
  return json(status, { error: fields ? { code, message, fields } : { code, message } });
}

type Item = Record<string, unknown> & { id: string };

interface ResourceSpec {
  prefix: string;
  fields: string[];
  positive?: string[];
  nonNegative?: string[];
  /** Bills, debts and goals carry `reserved_cents` (ADR 0011). */
  reserved?: boolean;
}

const RESOURCES: Record<string, ResourceSpec> = {
  '/income-sources': {
    prefix: 'income',
    fields: ['name', 'expected_amount_cents', 'schedule'],
    positive: ['expected_amount_cents'],
  },
  '/bills': {
    prefix: 'bill',
    fields: ['name', 'amount_cents', 'priority', 'first_due_date', 'repeat_every_months'],
    positive: ['amount_cents', 'priority'],
    reserved: true,
  },
  '/essential-expenses': {
    prefix: 'essential',
    fields: ['name', 'amount_per_period_cents'],
    positive: ['amount_per_period_cents'],
  },
  '/debts': {
    prefix: 'debt',
    fields: ['name', 'balance_cents', 'apr_bps', 'minimum_payment_cents', 'due_day'],
    nonNegative: ['balance_cents', 'apr_bps', 'minimum_payment_cents'],
    positive: ['due_day'],
    reserved: true,
  },
  '/goals': {
    prefix: 'goal',
    fields: ['name', 'kind', 'target_cents', 'current_cents', 'priority', 'deadline'],
    positive: ['target_cents', 'priority'],
    nonNegative: ['current_cents'],
    reserved: true,
  },
};

const NOW = '2026-11-19T20:00:00Z';

/** The checks whose 422s the app must place next to the right field. */
function validate(spec: ResourceSpec, body: Record<string, unknown>): Record<string, string> {
  const problems: Record<string, string> = {};
  for (const field of spec.fields) {
    if (!(field in body)) problems[field] = 'Field required';
  }
  for (const field of Object.keys(body)) {
    if (!spec.fields.includes(field)) problems[field] = 'Extra inputs are not permitted';
  }
  if (typeof body.name === 'string' && body.name.trim() === '') {
    problems.name = 'String should have at least 1 character';
  }
  for (const field of spec.positive ?? []) {
    if (typeof body[field] === 'number' && (body[field] as number) <= 0) {
      problems[field] = 'Input should be greater than 0';
    }
  }
  for (const field of spec.nonNegative ?? []) {
    if (typeof body[field] === 'number' && (body[field] as number) < 0) {
      problems[field] = 'Input should be greater than or equal to 0';
    }
  }
  const schedule = body.schedule as Record<string, unknown> | undefined;
  if (schedule && (schedule.type === 'weekly' || schedule.type === 'biweekly')) {
    if (!schedule.anchor_date) problems[`schedule.${schedule.type}.anchor_date`] = 'Field required';
  }
  return problems;
}

function validationError(problems: Record<string, string>): Response {
  const names = Object.keys(problems).sort();
  return error(422, 'validation_error', `Check these fields: ${names.join(', ')}`, problems);
}

interface FailOptions {
  /** With a code, the error envelope; without, a bare text body like a crash or a gateway. */
  code?: string;
  message?: string;
  /** How many requests in a row fail. Queries retry once, so 2 makes a query fail; Infinity, always. */
  times?: number;
}

const SEMI_MONTHLY_RULE =
  'Pick two paydays at least 7 days apart in every month, counting from the second ' +
  "payday to the next month's first: the 1st and 15th work, the 1st and 31st don't.";

export function createFakeBackend() {
  let serial = 0;
  const passwords = new Map<string, string>();
  const families = new Map<number, Family>();
  const refreshTokens = new Map<string, { family: number; state: RefreshTokenState }>();
  const accessTokens = new Map<string, { family: number; expired: boolean }>();
  let refreshGate: Promise<void> | null = null;
  const heldNext = new Map<string, Promise<void>>();
  const lostResponses = new Set<string>();
  const failures = new Map<string, { remaining: number; respond: () => Response }>();
  /** Each user's resources, by collection path such as "/bills". */
  const data = new Map<string, Map<string, Item[]>>();
  let idSerial = 0;

  /**
   * Accounts made with Sign in with Apple, by Apple user ID, with the name the first sign-in
   * sent. Internally such an account is keyed `apple:<id>` wherever others use the email.
   */
  const appleAccounts = new Map<string, { displayName: string | null }>();

  /** Each user's settings, by email, as PUT /me/settings stores them. */
  const settings = new Map<string, { timezone: string; no_deadline_goal_share_bps: number }>();
  const planning = createFakePlanning({
    json,
    error,
    items: (email, path) => collection(email, path),
  });

  function collection(email: string, path: string): Item[] {
    let byPath = data.get(email);
    if (!byPath) {
      byPath = new Map();
      data.set(email, byPath);
    }
    let items = byPath.get(path);
    if (!items) {
      items = [];
      byPath.set(path, items);
    }
    return items;
  }

  function newItem(path: string, body: Record<string, unknown>): Item {
    const spec = RESOURCES[path];
    idSerial += 1;
    return {
      id: `${spec?.prefix ?? 'snapshot'}-${idSerial}`,
      ...body,
      ...(spec?.reserved ? { reserved_cents: 0 } : {}),
      created_at: NOW,
      updated_at: NOW,
    };
  }

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

    /** Apple IDs that have signed in, with the name their first sign-in sent. */
    appleAccounts,

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

    /** The payday routes: set `planning.template` and paydays before planning. */
    planning,

    /** As if PUT /me/settings had already stored these. */
    setSettings(email: string, value: { timezone: string; no_deadline_goal_share_bps: number }) {
      settings.set(email, value);
    },

    /** A user's settings (time zone and goal share). */
    settingsFor(email: string) {
      return settings.get(email) ?? { timezone: 'UTC', no_deadline_goal_share_bps: 2000 };
    },

    /** The next request matching `call` is applied, but its response is lost (see handle). */
    loseResponseNext(call: string): void {
      lostResponses.add(call);
    },

    count(call: string): number {
      return backend.calls.filter((c) => c === call).length;
    },

    /** Every POST and PUT body, in arrival order, with its call ("PUT /bills/bill-1"). */
    bodies: [] as { call: string; body: unknown }[],

    /** The body of the last request matching `call`. */
    lastBody(call: string): unknown {
      return backend.bodies.filter((b) => b.call === call).at(-1)?.body;
    },

    /** Stores an item for a user, as if they had created it. Returns it with its id. */
    seed(email: string, path: string, body: Record<string, unknown>): Item {
      if (path === '/balance-snapshots') {
        const item = { ...newItem(path, body), as_of: NOW };
        collection(email, path).unshift(item); // newest first
        return item;
      }
      const item = newItem(path, body);
      collection(email, path).push(item);
      return item;
    },

    /** What a user has stored at `path`. */
    items(email: string, path: string): Item[] {
      return collection(email, path);
    },

    /**
     * The next request matching `call` gets this status instead: with the error envelope
     * when `code` is given, or as a bare text body (a crash, a gateway) when not.
     */
    failNext(
      call: string,
      status: number,
      { code, message = 'Something went wrong.', times = 1 }: FailOptions = {},
    ): void {
      failures.set(call, {
        remaining: times,
        respond: () =>
          code ? error(status, code, message) : new Response('Internal Server Error', { status }),
      });
    },

    /** Honors the client's abort signal, so a request that never answers can time out. */
    fetch: jest.fn((request: Request, init?: RequestInit): Promise<Response> => {
      const aborted = new Promise<never>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new Error('Aborted')));
      });
      return Promise.race([handle(request), aborted]);
    }),
  };

  /**
   * Like the server applying a request and the reply never reaching the phone (a timeout or
   * a dropped connection): the work is done, then the fetch fails as with no signal.
   */
  async function handle(request: Request): Promise<Response> {
    const call = `${request.method} ${request.url.slice(BASE_URL.length).split('?')[0]}`;
    const response = await route(request);
    if (lostResponses.delete(call)) {
      throw new TypeError('Network request failed');
    }
    return response;
  }

  async function route(request: Request): Promise<Response> {
    if (backend.offline) {
      throw new TypeError('Network request failed');
    }
    const url = request.url.slice(BASE_URL.length);
    const path = url.split('?')[0] ?? url;
    const call = `${request.method} ${path}`;
    backend.calls.push(call);
    const hasBody = request.method === 'POST' || request.method === 'PUT';
    const text = hasBody ? await request.text() : '';
    const body = text ? JSON.parse(text) : {};
    if (hasBody) {
      backend.bodies.push({ call, body });
    }
    const held = heldNext.get(call);
    if (held) {
      heldNext.delete(call);
      await held;
    }
    const failure = failures.get(call);
    if (failure) {
      failure.remaining -= 1;
      if (failure.remaining <= 0) {
        failures.delete(call);
      }
      return failure.respond();
    }

    switch (call) {
      case 'POST /auth/register':
        return register(body);
      case 'POST /auth/login':
        return login(body);
      case 'POST /auth/apple':
        return appleSignIn(body);
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
      default: {
        const handled = planningRoute(request, path, body);
        return handled ?? resource(request, path, body);
      }
    }
  }

  function planningRoute(
    request: Request,
    path: string,
    body: Record<string, unknown>,
  ): Response | null {
    const isSettings = request.method === 'PUT' && path === '/me/settings';
    const isPlanning =
      path === '/dashboard' ||
      path.startsWith('/plans') ||
      /^\/income-sources\/[^/]+\/paychecks\//.test(path) ||
      /^\/(bills|debts)\/[^/]+\/payments(\/[^/]+\/undo)?$/.test(path);
    if (!isSettings && !isPlanning) {
      return null;
    }
    const email = authorize(request);
    if (typeof email !== 'string') {
      return email;
    }
    if (isSettings) {
      settings.set(email, {
        timezone: String(body.timezone),
        no_deadline_goal_share_bps: Number(body.no_deadline_goal_share_bps),
      });
      planning.bump(email);
      return me(request.headers.get('Authorization'));
    }
    return planning.handle(request.method, path, body, email);
  }

  /** The signed-in user's email, or the 401 the real API would send. */
  function authorize(request: Request): string | Response {
    const raw = request.headers.get('Authorization')?.replace(/^Bearer /, '');
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
    return families.get(token.family)?.email ?? '';
  }

  function resource(request: Request, path: string, body: Record<string, unknown>): Response {
    const [, name = '', id] = path.split('/');
    const collectionPath = `/${name}`;
    const spec = RESOURCES[collectionPath];
    const isBalance = collectionPath === '/balance-snapshots';
    if (!spec && !isBalance) {
      return error(404, 'not_found', 'Not found.');
    }
    const email = authorize(request);
    if (typeof email !== 'string') {
      return email;
    }
    const items = collection(email, collectionPath);

    if (isBalance || !spec) {
      if (request.method === 'GET' && !id) {
        return json(200, { items });
      }
      if (request.method === 'POST' && !id) {
        if (typeof body.amount_cents !== 'number') {
          return validationError({ amount_cents: 'Field required' });
        }
        if (items[0]?.amount_cents !== body.amount_cents) {
          planning.bump(email); // the same amount again leaves drafts current, as in the hash
        }
        return json(201, backend.seed(email, collectionPath, { amount_cents: body.amount_cents }));
      }
      return error(405, 'method_not_allowed', 'Method Not Allowed');
    }

    const index = id ? items.findIndex((item) => item.id === id) : -1;
    if (id && index < 0) {
      return error(404, 'not_found', 'Not found.');
    }
    if (request.method === 'GET') {
      return id ? json(200, items[index]) : json(200, { items });
    }
    if (request.method === 'DELETE' && id) {
      items.splice(index, 1);
      planning.bump(email);
      return new Response(null, { status: 204 });
    }
    const isCreate = request.method === 'POST' && !id;
    const isReplace = request.method === 'PUT' && Boolean(id);
    if (!isCreate && !isReplace) {
      return error(405, 'method_not_allowed', 'Method Not Allowed');
    }
    const problems = validate(spec, body);
    if (Object.keys(problems).length) {
      return validationError(problems);
    }
    const refused = businessRule(collectionPath, body, items, id);
    if (refused) {
      return refused;
    }
    planning.bump(email);
    if (isCreate) {
      const item = newItem(collectionPath, body);
      items.push(item);
      return json(201, item);
    }
    const updated: Item = { ...items[index], ...body, id: id ?? '', updated_at: NOW };
    items[index] = updated;
    return json(200, updated);
  }

  /** The two rules whose errors are about the whole form rather than one field. */
  function businessRule(
    path: string,
    body: Record<string, unknown>,
    items: Item[],
    id: string | undefined,
  ): Response | null {
    const schedule = body.schedule as Record<string, unknown> | undefined;
    if (path === '/income-sources' && schedule?.type === 'semi_monthly') {
      const first = Number(schedule.first_day_of_month);
      const second = Number(schedule.second_day_of_month);
      if (second - first < 7 || first + 31 - second < 7) {
        return error(422, 'invalid_input', SEMI_MONTHLY_RULE);
      }
    }
    const isSecondEmergency =
      path === '/goals' &&
      body.kind === 'emergency' &&
      items.some((item) => item.kind === 'emergency' && item.id !== id);
    if (isSecondEmergency) {
      return error(
        409,
        'emergency_goal_exists',
        'You already have an emergency fund goal. Change that one instead.',
      );
    }
    return null;
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

  /**
   * Like the real /auth/apple (ADR 0019): the token must carry the hash of the raw nonce sent
   * with it, the account is found by Apple user ID, and the name is kept from the first time.
   */
  function appleSignIn(body: {
    identity_token: string;
    nonce: string;
    full_name?: string | null;
  }): Response {
    const [kind, appleUserId, nonceHash] = body.identity_token.split('|');
    if (kind !== 'apple-identity' || !appleUserId || nonceHash !== sha256Hex(body.nonce)) {
      return error(401, 'invalid_apple_token', "Sign in with Apple didn't work. Try again.");
    }
    if (!appleAccounts.has(appleUserId)) {
      appleAccounts.set(appleUserId, { displayName: body.full_name ?? null });
    }
    serial += 1;
    families.set(serial, { email: `apple:${appleUserId}`, revoked: false });
    return json(200, issue(serial));
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
    const account = families.get(token.family)?.email ?? '';
    const apple = account.startsWith('apple:') ? appleAccounts.get(account.slice(6)) : undefined;
    const user: UserResponse = {
      id: `user-${account}`,
      email: apple ? null : account,
      display_name: apple ? apple.displayName : null,
      ...backend.settingsFor(account),
      created_at: '2026-11-01T00:00:00Z',
    };
    return json(200, user);
  }

  globalThis.fetch = backend.fetch as unknown as typeof globalThis.fetch;
  return backend;
}

export type FakeBackend = ReturnType<typeof createFakeBackend>;
