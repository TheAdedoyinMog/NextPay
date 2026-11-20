import { QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';

import { SessionProvider } from '@/features/auth/SessionProvider';
import type { FakeBackend } from '@/test/fakeBackend';
import { createTestQueryClient, EMAIL, signedInBackend } from '@/test/hooks';

import { OnboardingProvider, useFinishOnboarding, useOnboardingDecision } from './OnboardingGate';

jest.mock('@/api/config', () => ({ API_BASE_URL: 'http://api.test' }));
jest.mock('expo-secure-store', () => jest.requireActual('@/test/fakeSecureStore'));

let backend: FakeBackend;

beforeEach(async () => {
  backend = await signedInBackend();
});

async function renderGate() {
  const queryClient = createTestQueryClient();
  function wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <SessionProvider>
          <OnboardingProvider>{children}</OnboardingProvider>
        </SessionProvider>
      </QueryClientProvider>
    );
  }
  return renderHook(() => ({ decision: useOnboardingDecision(), finish: useFinishOnboarding() }), {
    wrapper,
  });
}

it('opens the app for an account with income', async () => {
  backend.seed(EMAIL, '/income-sources', {
    name: 'Acme',
    expected_amount_cents: 100,
    schedule: { type: 'monthly', day_of_month: 1 },
  });
  const { result } = await renderGate();

  await waitFor(() => expect(result.current.decision).toBe('done'));
});

it('onboards an account with no income, until finished', async () => {
  const { result } = await renderGate();

  await waitFor(() => expect(result.current.decision).toBe('onboarding'));
  await act(async () => result.current.finish());
  expect(result.current.decision).toBe('done');
});

it('opens the app when it can’t tell, such as offline', async () => {
  backend.failNext('GET /income-sources', 503, { times: 2 });
  const { result } = await renderGate();

  await waitFor(() => expect(result.current.decision).toBe('done'));
});
