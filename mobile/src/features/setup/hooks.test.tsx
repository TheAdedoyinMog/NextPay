/**
 * Bills, essentials and debts have the same hook shape, so one table runs the same checks on
 * each: list, create, replace (whole resource on PUT), delete, and invalidation of planning.
 * Income, balance and goals have their own files, for what is special about them.
 */
import { act, waitFor } from '@testing-library/react-native';

import * as bills from '@/features/bills/api';
import * as debts from '@/features/debts/api';
import * as essentials from '@/features/essentials/api';
import { planningKeys } from '@/features/planning/keys';
import type { FakeBackend } from '@/test/fakeBackend';
import { EMAIL, renderWithClient, signedInBackend } from '@/test/hooks';

jest.mock('@/api/config', () => ({ API_BASE_URL: 'http://api.test' }));
jest.mock('expo-secure-store', () => jest.requireActual('@/test/fakeSecureStore'));

type Hooks = {
  list: { data?: { id: string; name: string }[]; isSuccess: boolean };
  create: { mutateAsync: (body: never) => Promise<unknown> };
  update: { mutateAsync: (args: { id: string; body: never }) => Promise<unknown> };
  remove: { mutateAsync: (id: string) => Promise<unknown> };
};

const cases = [
  {
    resource: 'bills',
    path: '/bills',
    use: (): Hooks => ({
      list: bills.useBills(),
      create: bills.useCreateBill(),
      update: bills.useUpdateBill(),
      remove: bills.useDeleteBill(),
    }),
    body: {
      name: 'Rent',
      amount_cents: 120000,
      priority: 1,
      first_due_date: '2026-12-01',
      repeat_every_months: 1,
    },
    // A one-off: the nullable field is sent, as null.
    replacement: {
      name: 'Rent',
      amount_cents: 125000,
      priority: 1,
      first_due_date: '2026-12-01',
      repeat_every_months: null,
    },
  },
  {
    resource: 'essentials',
    path: '/essential-expenses',
    use: (): Hooks => ({
      list: essentials.useEssentials(),
      create: essentials.useCreateEssential(),
      update: essentials.useUpdateEssential(),
      remove: essentials.useDeleteEssential(),
    }),
    body: { name: 'Groceries', amount_per_period_cents: 15000 },
    replacement: { name: 'Groceries', amount_per_period_cents: 17550 },
  },
  {
    resource: 'debts',
    path: '/debts',
    use: (): Hooks => ({
      list: debts.useDebts(),
      create: debts.useCreateDebt(),
      update: debts.useUpdateDebt(),
      remove: debts.useDeleteDebt(),
    }),
    body: {
      name: 'Visa',
      balance_cents: 250000,
      apr_bps: 2499,
      minimum_payment_cents: 3500,
      due_day: 15,
    },
    replacement: {
      name: 'Visa',
      balance_cents: 240000,
      apr_bps: 0,
      minimum_payment_cents: 3500,
      due_day: 31,
    },
  },
];

let backend: FakeBackend;

beforeEach(async () => {
  backend = await signedInBackend();
});

describe.each(cases)('$resource', ({ path, use, body, replacement }) => {
  it('lists what the user has', async () => {
    backend.seed(EMAIL, path, body);
    const { result } = await renderWithClient(use);

    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));
    expect(result.current.list.data?.map((item) => item.name)).toEqual([body.name]);
  });

  it('creates, then refetches the list and marks planning stale', async () => {
    const { result, queryClient } = await renderWithClient(use);
    await waitFor(() => expect(result.current.list.data).toEqual([]));
    queryClient.setQueryData(planningKeys.paychecks(), []);

    await act(() => result.current.create.mutateAsync(body as never));

    expect(backend.lastBody(`POST ${path}`)).toEqual(body);
    expect(result.current.list.data).toHaveLength(1);
    expect(queryClient.getQueryState(planningKeys.paychecks())?.isInvalidated).toBe(true);
  });

  it('replaces the whole resource on PUT', async () => {
    const item = backend.seed(EMAIL, path, body);
    const { result } = await renderWithClient(use);
    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));

    await act(() => result.current.update.mutateAsync({ id: item.id, body: replacement as never }));

    expect(backend.lastBody(`PUT ${path}/${item.id}`)).toEqual(replacement);
    expect(result.current.list.data?.[0]).toMatchObject(replacement);
  });

  it('deletes, and the list no longer has it', async () => {
    const item = backend.seed(EMAIL, path, body);
    const { result } = await renderWithClient(use);
    await waitFor(() => expect(result.current.list.data).toHaveLength(1));

    await act(() => result.current.remove.mutateAsync(item.id));

    expect(result.current.list.data).toEqual([]);
  });

  it('rejects a PUT that leaves a field out, naming it', async () => {
    const item = backend.seed(EMAIL, path, body);
    const { result } = await renderWithClient(use);
    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));
    const [missing, ...rest] = Object.keys(replacement);
    const partial = Object.fromEntries(
      rest.map((key) => [key, (replacement as Record<string, unknown>)[key]]),
    );

    const error = await act(() =>
      result.current.update
        .mutateAsync({ id: item.id, body: partial as never })
        .catch((e: unknown) => e),
    );

    expect(error).toMatchObject({ status: 422, fields: { [missing as string]: 'Field required' } });
  });
});
