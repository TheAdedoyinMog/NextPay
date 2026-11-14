import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react-native';

import { DevStatus } from './DevStatus';

jest.mock('@/api/config', () => ({ API_BASE_URL: 'http://api.test' }));

async function renderScreen() {
  const client = new QueryClient({
    // No retry delay, and no cache-cleanup timer left running after the test.
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  await render(
    <QueryClientProvider client={client}>
      <DevStatus />
    </QueryClientProvider>,
  );
}

it('shows the status and engine version', async () => {
  globalThis.fetch = jest.fn().mockResolvedValue(
    new Response(JSON.stringify({ status: 'ok', engine_version: '1.2.3' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  );

  await renderScreen();

  expect(await screen.findByText('ok')).toBeTruthy();
  expect(screen.getByText('1.2.3')).toBeTruthy();
});

it('shows why it could not connect', async () => {
  globalThis.fetch = jest.fn().mockRejectedValue(new TypeError('Network request failed'));

  await renderScreen();

  expect(await screen.findByText('Could not reach the server at http://api.test.')).toBeTruthy();
});
