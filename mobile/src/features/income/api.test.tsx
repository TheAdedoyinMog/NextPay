import { act, waitFor } from '@testing-library/react-native';

import { planningKeys } from '@/features/planning/keys';
import type { FakeBackend } from '@/test/fakeBackend';
import { EMAIL, renderWithClient, signedInBackend } from '@/test/hooks';

import {
  type IncomeSourceRequest,
  useCreateIncomeSource,
  useDeleteIncomeSource,
  useIncomeSources,
  useUpdateIncomeSource,
} from './api';

jest.mock('@/api/config', () => ({ API_BASE_URL: 'http://api.test' }));
jest.mock('expo-secure-store', () => jest.requireActual('@/test/fakeSecureStore'));

const JOB: IncomeSourceRequest = {
  name: 'Acme payroll',
  expected_amount_cents: 150000,
  schedule: { type: 'biweekly', anchor_date: '2026-11-20' },
};

let backend: FakeBackend;

beforeEach(async () => {
  backend = await signedInBackend();
});

function useIncome() {
  return {
    list: useIncomeSources(),
    create: useCreateIncomeSource(),
    update: useUpdateIncomeSource(),
    remove: useDeleteIncomeSource(),
  };
}

it('lists the user’s income sources', async () => {
  backend.seed(EMAIL, '/income-sources', JOB);
  const { result } = await renderWithClient(useIncome);

  await waitFor(() => expect(result.current.list.isSuccess).toBe(true));
  expect(result.current.list.data?.map((s) => s.name)).toEqual(['Acme payroll']);
});

it('creates one, then refetches the list and marks planning stale', async () => {
  const { result, queryClient } = await renderWithClient(useIncome);
  await waitFor(() => expect(result.current.list.data).toEqual([]));
  queryClient.setQueryData([...planningKeys.plans(), 'plan-1'], { id: 'plan-1' });

  await act(() => result.current.create.mutateAsync(JOB));

  expect(backend.lastBody('POST /income-sources')).toEqual(JOB);
  expect(result.current.list.data?.map((s) => s.name)).toEqual(['Acme payroll']);
  expect(queryClient.getQueryState([...planningKeys.plans(), 'plan-1'])?.isInvalidated).toBe(true);
});

it('replaces the whole source on PUT, schedule included', async () => {
  const source = backend.seed(EMAIL, '/income-sources', JOB);
  const { result } = await renderWithClient(useIncome);
  await waitFor(() => expect(result.current.list.isSuccess).toBe(true));
  const body: IncomeSourceRequest = {
    name: 'Acme payroll',
    expected_amount_cents: 160000,
    schedule: { type: 'monthly', day_of_month: 31 },
  };

  await act(() => result.current.update.mutateAsync({ id: source.id, body }));

  expect(backend.lastBody(`PUT /income-sources/${source.id}`)).toEqual(body);
  expect(result.current.list.data?.[0]?.schedule).toEqual({ type: 'monthly', day_of_month: 31 });
});

it('removes one from the list (the backend deletes or archives it)', async () => {
  const source = backend.seed(EMAIL, '/income-sources', JOB);
  const { result } = await renderWithClient(useIncome);
  await waitFor(() => expect(result.current.list.data).toHaveLength(1));

  await act(() => result.current.remove.mutateAsync(source.id));

  expect(backend.calls).toContain(`DELETE /income-sources/${source.id}`);
  expect(result.current.list.data).toEqual([]);
});

it('rejects with the 422’s fields, and leaves the list alone', async () => {
  const { result } = await renderWithClient(useIncome);
  await waitFor(() => expect(result.current.list.isSuccess).toBe(true));

  const error = await act(() =>
    result.current.create
      .mutateAsync({ ...JOB, expected_amount_cents: 0 })
      .catch((e: unknown) => e),
  );

  expect(error).toMatchObject({
    status: 422,
    fields: { expected_amount_cents: 'Input should be greater than 0' },
  });
  expect(backend.items(EMAIL, '/income-sources')).toEqual([]);
});
