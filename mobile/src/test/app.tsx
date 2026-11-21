/**
 * The whole app from launch (the real routes in src/app, session and client) against the
 * fake backend. A test file using this must also declare these mocks, since jest.mock calls
 * can't live in a helper:
 *
 *   jest.mock('@/api/config', () => ({ API_BASE_URL: 'http://api.test' }));
 *   jest.mock('expo-secure-store', () => jest.requireActual('@/test/fakeSecureStore'));
 *   jest.mock('expo-splash-screen', () => jest.requireActual('@/test/app').splashScreenMock);
 *   jest.mock('@/api/queryClient', () => jest.requireActual('@/test/app').queryClientMock());
 *
 * and call `afterEach(settle)`.
 */
import type { QueryClient } from '@tanstack/react-query';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { session } from '@/api/session';

import { createFakeBackend, type FakeBackend } from './fakeBackend';
import * as keychain from './fakeSecureStore';

export const EMAIL = 'ada@example.com';

export const splashScreenMock = {
  preventAutoHideAsync: async () => true,
  hideAsync: async () => undefined,
};

// A global, because the jest.mock factory and the test may hold different module instances.
const clients: QueryClient[] = ((
  globalThis as { __testQueryClients?: QueryClient[] }
).__testQueryClients ??= []);

/**
 * Waits until every query client the app made is idle. A test that ends while a refetch is in
 * flight would otherwise send it to the next test's backend, which answers at the same fetch.
 */
export async function settle() {
  await waitFor(() =>
    expect(clients.every((client) => client.isFetching() === 0 && client.isMutating() === 0)).toBe(
      true,
    ),
  );
  clients.length = 0;
}

/**
 * What every setup mutation does on success (invalidateAfterSetupChange): marks planning
 * queries stale, so open screens refetch. For a change made elsewhere, such as another device.
 */
export async function setupChangedElsewhere() {
  await Promise.all(clients.map((client) => client.invalidateQueries({ queryKey: ['planning'] })));
}

/** The app's real query client, minus the cache-cleanup timer that would outlive each test. */
export function queryClientMock() {
  const actual = jest.requireActual('@/api/queryClient');
  return {
    ...actual,
    createQueryClient: () => {
      const client = actual.createQueryClient();
      clients.push(client);
      const defaults = client.getDefaultOptions();
      client.setDefaultOptions({
        ...defaults,
        queries: { ...defaults.queries, gcTime: Infinity, retryDelay: 0 },
        mutations: { ...defaults.mutations, gcTime: Infinity },
      });
      return client;
    },
  };
}

export const JOB = {
  name: 'Acme payroll',
  expected_amount_cents: 150000,
  schedule: { type: 'biweekly', anchor_date: '2026-11-20' },
};

/**
 * A fresh backend and a phone holding Ada's session, as after an earlier run. The session
 * object outlives each test, so the last test's session is ended first: otherwise the next
 * launch would start out signed in, before the app restores from the Keychain.
 */
export async function setUp({ withIncome }: { withIncome: boolean }): Promise<FakeBackend> {
  await session.signOut();
  keychain.reset();
  const backend = createFakeBackend();
  if (withIncome) {
    backend.seed(EMAIL, '/income-sources', JOB);
  }
  const tokens = backend.issueSession(EMAIL);
  keychain.items.set(keychain.REFRESH_TOKEN_KEY, tokens.refresh_token);
  return backend;
}

/** Opens the app as on a cold start: the session is restored from the Keychain. */
export function launch() {
  return renderRouter('src/app', { initialUrl: '/' });
}

/** From Home, opens a setup list such as "income" through its "Manage" link. */
export async function openFromHome(section: string) {
  await fireEvent.press(await screen.findByRole('button', { name: `Manage ${section}` }));
}

export async function type(label: string, text: string) {
  await fireEvent.changeText(screen.getByLabelText(label), text);
}

export async function press(name: string | RegExp) {
  await fireEvent.press(screen.getByRole('button', { name }));
}

/** Picks an option in a select field's sheet: `choose("How often you're paid", 'Once a month')`. */
export async function choose(label: string, option: string) {
  await fireEvent.press(screen.getByRole('button', { name: new RegExp(`^${label}:`) }));
  await fireEvent.press(screen.getByRole('radio', { name: option }));
}
