/**
 * The one place the app talks HTTP: base URL, auth header, refresh-and-retry, timeout, and
 * error mapping (ADR 0012, ADR 0013). Feature hooks call `unwrap(api.GET('/path'))` and get
 * typed data or an `ApiError`.
 */
import createClient from 'openapi-fetch';

import { API_BASE_URL } from './config';
import type { components, paths } from './schema';

const REQUEST_TIMEOUT_MS = 15_000;

/** A 5xx is never the user's fault, and a raw status code reads as broken. */
export const SERVER_ERROR_MESSAGE = 'Something went wrong on our side. Try again in a moment.';
const UNEXPECTED_ERROR_MESSAGE = 'Something went wrong. Try again.';

type ErrorResponse = components['schemas']['ErrorResponse'];

export class ApiError extends Error {
  constructor(
    /** The HTTP status, or 0 when no response arrived. */
    readonly status: number,
    /** The backend's error code, such as `validation_error`, or `network_error` / `timeout`. */
    readonly code: string,
    message: string,
    /**
     * On a 422 `validation_error`: each rejected field's dotted path (such as `amount_cents` or
     * `schedule.weekly.anchor_date`) with what was wrong. Empty otherwise.
     */
    readonly fields: Readonly<Record<string, string>> = {},
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * What the client needs from the session, so it never knows where tokens are kept.
 * Both methods may throw an `ApiError` (for example when a refresh can't reach the server).
 */
export interface AuthHandler {
  /** The access token to send, refreshing first if signed in without one; null when signed out. */
  getAccessToken(): Promise<string | null>;
  /** A request sent with `rejected` got a 401. Resolves the token to retry with, or null. */
  refreshAccessToken(rejected: string): Promise<string | null>;
}

const signedOut: AuthHandler = {
  getAccessToken: async () => null,
  refreshAccessToken: async () => null,
};

let auth: AuthHandler = signedOut;

/** The session plugs in here (src/api/session.ts). */
export function setAuthHandler(handler: AuthHandler): void {
  auth = handler;
}

class RequestTimeoutError extends Error {}

async function fetchWithTimeout(request: Request): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await globalThis.fetch(request, { signal: controller.signal });
  } catch (error) {
    throw controller.signal.aborted ? new RequestTimeoutError() : error;
  } finally {
    clearTimeout(timer);
  }
}

/** /auth/* takes credentials in the body, and its 401s mean "wrong credentials", not "refresh". */
function isAuthRoute(request: Request): boolean {
  return request.url.startsWith(`${API_BASE_URL}/auth/`);
}

function withToken(request: Request, token: string): Request {
  request.headers.set('Authorization', `Bearer ${token}`);
  return request;
}

/**
 * Sends the access token. On a 401, asks the session for a fresh one and retries once.
 * The session makes sure concurrent 401s share a single refresh (ADR 0009 forbids two).
 */
async function fetchWithAuth(request: Request): Promise<Response> {
  if (isAuthRoute(request)) {
    return fetchWithTimeout(request);
  }
  const token = await auth.getAccessToken();
  if (!token) {
    return fetchWithTimeout(request);
  }
  const retry = request.clone(); // before sending: sending consumes the body
  const response = await fetchWithTimeout(withToken(request, token));
  if (response.status !== 401) {
    return response;
  }
  const freshToken = await auth.refreshAccessToken(token);
  if (!freshToken) {
    return response;
  }
  return fetchWithTimeout(withToken(retry, freshToken));
}

export const api = createClient<paths>({ baseUrl: API_BASE_URL, fetch: fetchWithAuth });

function isErrorResponse(body: unknown): body is ErrorResponse {
  const error = (body as Partial<ErrorResponse> | null | undefined)?.error;
  return typeof error?.code === 'string' && typeof error.message === 'string';
}

function noResponseError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error; // already mapped, e.g. by a refresh that failed
  }
  if (error instanceof RequestTimeoutError) {
    return new ApiError(0, 'timeout', `The server at ${API_BASE_URL} took too long to answer.`);
  }
  return new ApiError(0, 'network_error', `Could not reach the server at ${API_BASE_URL}.`);
}

/** Returns a call's data, or throws an `ApiError` for anything else. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result: Awaited<typeof call>;
  try {
    result = await call;
  } catch (error) {
    throw noResponseError(error);
  }
  const { data, error, response } = result;
  if (!response.ok) {
    if (isErrorResponse(error)) {
      const { code, message, fields } = error.error;
      throw new ApiError(response.status, code, message, fields ?? {});
    }
    // No envelope: a crash, a proxy, or a gateway. The status stays on the error for tests.
    const message = response.status >= 500 ? SERVER_ERROR_MESSAGE : UNEXPECTED_ERROR_MESSAGE;
    throw new ApiError(response.status, 'http_error', message);
  }
  return data as T;
}

/** A message that is safe to show: the backend's own, or the client's for no response. */
export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : UNEXPECTED_ERROR_MESSAGE;
}
