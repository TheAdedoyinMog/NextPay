import { QueryClient } from '@tanstack/react-query';

import { ApiError } from './client';

const MAX_QUERY_RETRIES = 1;

/** A 4xx will fail the same way again, so only network errors and 5xx are worth retrying. */
export function shouldRetryQuery(failureCount: number, error: Error): boolean {
  const isClientError = error instanceof ApiError && error.status >= 400 && error.status < 500;
  return !isClientError && failureCount < MAX_QUERY_RETRIES;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: shouldRetryQuery },
      // POST is not idempotent, so a retry could create a duplicate (ADR 0010).
      mutations: { retry: false },
    },
  });
}
