/**
 * The one place the app talks HTTP: base URL, auth header, timeout, error mapping (ADR 0012).
 * Feature hooks call `unwrap(api.GET('/path'))` and get typed data or an `ApiError`.
 */
import createClient from 'openapi-fetch';

import { API_BASE_URL } from './config';
import type { components, paths } from './schema';

const REQUEST_TIMEOUT_MS = 15_000;

type ErrorResponse = components['schemas']['ErrorResponse'];
type AccessTokenProvider = () => string | null | Promise<string | null>;

export class ApiError extends Error {
  constructor(
    /** The HTTP status, or 0 when no response arrived. */
    readonly status: number,
    /** The backend's error code, such as `validation_error`, or `network_error`. */
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

let getAccessToken: AccessTokenProvider = () => null;

/** Sign-in plugs in here, so the client never needs to know where tokens are kept. */
export function setAccessTokenProvider(provider: AccessTokenProvider): void {
  getAccessToken = provider;
}

async function fetchWithTimeout(request: Request): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await globalThis.fetch(request, { signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

export const api = createClient<paths>({ baseUrl: API_BASE_URL, fetch: fetchWithTimeout });

api.use({
  async onRequest({ request }) {
    const token = await getAccessToken();
    if (token) {
      request.headers.set('Authorization', `Bearer ${token}`);
    }
    return request;
  },
});

function isErrorResponse(body: unknown): body is ErrorResponse {
  const error = (body as Partial<ErrorResponse> | null | undefined)?.error;
  return typeof error?.code === 'string' && typeof error.message === 'string';
}

/** Returns a call's data, or throws an `ApiError` for anything else. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result: Awaited<typeof call>;
  try {
    result = await call;
  } catch {
    throw new ApiError(0, 'network_error', `Could not reach the server at ${API_BASE_URL}.`);
  }
  const { data, error, response } = result;
  if (!response.ok) {
    if (isErrorResponse(error)) {
      throw new ApiError(response.status, error.error.code, error.error.message);
    }
    throw new ApiError(
      response.status,
      'http_error',
      `The request failed with status ${response.status}.`,
    );
  }
  return data as T;
}
