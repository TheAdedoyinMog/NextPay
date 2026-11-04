import { ApiError } from './client';
import { createQueryClient, shouldRetryQuery } from './queryClient';

jest.mock('./config', () => ({ API_BASE_URL: 'http://api.test' }));

describe('shouldRetryQuery', () => {
  it.each([[400], [401], [404], [422]])('does not retry a %d', (status) => {
    expect(shouldRetryQuery(0, new ApiError(status, 'x', 'x'))).toBe(false);
  });

  it.each([
    ['a network error', new ApiError(0, 'network_error', 'x')],
    ['a 500', new ApiError(500, 'http_error', 'x')],
  ])('retries %s once', (_name, error) => {
    expect(shouldRetryQuery(0, error)).toBe(true);
    expect(shouldRetryQuery(1, error)).toBe(false);
  });
});

it('never retries a mutation', () => {
  expect(createQueryClient().getDefaultOptions().mutations?.retry).toBe(false);
});
