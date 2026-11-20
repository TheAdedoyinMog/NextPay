import { act, waitFor } from '@testing-library/react-native';

import { planningKeys } from '@/features/planning/keys';
import type { FakeBackend } from '@/test/fakeBackend';
import { EMAIL, renderWithClient, signedInBackend } from '@/test/hooks';

import { currentBalance, useBalanceSnapshots, useRecordBalance } from './api';

jest.mock('@/api/config', () => ({ API_BASE_URL: 'http://api.test' }));
jest.mock('expo-secure-store', () => jest.requireActual('@/test/fakeSecureStore'));

let backend: FakeBackend;

beforeEach(async () => {
  backend = await signedInBackend();
});

function useBalance() {
  return { list: useBalanceSnapshots(), record: useRecordBalance() };
}

it('has no current balance until one is entered', async () => {
  const { result } = await renderWithClient(useBalance);

  await waitFor(() => expect(result.current.list.isSuccess).toBe(true));
  expect(currentBalance(result.current.list.data ?? [])).toBeNull();
  expect(backend.calls).toContain('GET /balance-snapshots');
});

it('records a new snapshot, which becomes the current balance', async () => {
  backend.seed(EMAIL, '/balance-snapshots', { amount_cents: 50000 });
  const { result, queryClient } = await renderWithClient(useBalance);
  await waitFor(() => expect(result.current.list.data).toHaveLength(1));
  queryClient.setQueryData(planningKeys.paychecks(), []);

  await act(() => result.current.record.mutateAsync(-1234));

  expect(backend.lastBody('POST /balance-snapshots')).toEqual({ amount_cents: -1234 });
  expect(currentBalance(result.current.list.data ?? [])?.amount_cents).toBe(-1234);
  expect(result.current.list.data).toHaveLength(2);
  expect(queryClient.getQueryState(planningKeys.paychecks())?.isInvalidated).toBe(true);
});
