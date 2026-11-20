import { screen, waitFor } from 'expo-router/testing-library';
import { Alert } from 'react-native';

import { choose, EMAIL, launch, openFromHome, press, settle, setUp, type } from '@/test/app';
import type { FakeBackend } from '@/test/fakeBackend';

jest.mock('@/api/config', () => ({ API_BASE_URL: 'http://api.test' }));
jest.mock('expo-secure-store', () => jest.requireActual('@/test/fakeSecureStore'));
jest.mock('expo-splash-screen', () => jest.requireActual('@/test/app').splashScreenMock);
jest.mock('@/api/queryClient', () => jest.requireActual('@/test/app').queryClientMock());

let backend: FakeBackend;

beforeEach(async () => {
  backend = await setUp({ withIncome: true });
});

afterEach(async () => {
  jest.restoreAllMocks();
  await settle();
});

async function openIncomeList() {
  await launch();
  await waitFor(() => expect(screen.queryByTestId('deciding-cover')).toBeNull());
  await openFromHome('income');
  await screen.findByRole('button', { name: 'Add income' });
}

it('lists income with its schedule in words', async () => {
  await openIncomeList();

  expect(screen).toHavePathname('/setup/income');
  expect(screen.getByText('Every other Friday')).toBeTruthy(); // 2026-11-20 is a Friday
  expect(screen.getAllByText('$1,500.00').length).toBeGreaterThan(0);
});

it('adds a monthly income and returns to the list', async () => {
  await openIncomeList();
  await press('Add income');

  await type('Name', 'Side gig');
  await type('Take-home pay per paycheck', '0.29');
  await choose("How often you're paid", 'Once a month');
  await type('Day of the month', '31');
  await press('Add income');

  expect(await screen.findByText('Side gig')).toBeTruthy();
  expect(screen.getByText('The 31st of each month')).toBeTruthy();
  expect(screen).toHavePathname('/setup/income');
  expect(backend.lastBody('POST /income-sources')).toEqual({
    name: 'Side gig',
    expected_amount_cents: 29,
    schedule: { type: 'monthly', day_of_month: 31 },
  });
});

it('edits by sending the whole source on PUT', async () => {
  const [source] = backend.items(EMAIL, '/income-sources');
  await openIncomeList();
  await press('Acme payroll');

  expect(screen.getByLabelText('Take-home pay per paycheck').props.value).toBe('1500.00');
  expect(screen.getByRole('button', { name: 'A payday: Nov 20, 2026' })).toBeTruthy();
  await type('Take-home pay per paycheck', '1612.50');
  await press('Save changes');

  expect(await screen.findByText('$1,612.50')).toBeTruthy();
  expect(backend.lastBody(`PUT /income-sources/${source?.id}`)).toEqual({
    name: 'Acme payroll',
    expected_amount_cents: 161250,
    schedule: { type: 'biweekly', anchor_date: '2026-11-20' },
  });
});

it('shows a rule the form can’t check, such as paydays too close together', async () => {
  await openIncomeList();
  await press('Acme payroll');
  await choose("How often you're paid", 'Twice a month');
  await type('First payday of the month', '1');
  await type('Second payday of the month', '31');

  await press('Save changes');

  expect(await screen.findByText(/at least 7 days apart in every month/)).toBeTruthy();
});

it('removes a source only after confirming', async () => {
  const alert = jest.spyOn(Alert, 'alert');
  await openIncomeList();
  await press('Acme payroll');

  await press('Remove income source');
  expect(alert).toHaveBeenCalledWith(
    'Remove Acme payroll?',
    'It stops counting as income. Any paychecks already recorded stay in your history.',
    expect.any(Array),
  );
  expect(backend.calls.some((call) => call.startsWith('DELETE'))).toBe(false);
  const buttons = alert.mock.calls[0]?.[2] ?? [];
  buttons.find((button) => button.text === 'Remove')?.onPress?.();

  expect(await screen.findByText('No income yet')).toBeTruthy();
  expect(screen).toHavePathname('/setup/income');
});

it('shows a friendly error with a retry when the list fails to load', async () => {
  // Twice: the first attempt and the one automatic retry.
  backend.failNext('GET /income-sources', 503, { times: 2 });

  await launch();

  const alert = await screen.findByText('Something went wrong on our side. Try again in a moment.');
  expect(alert).toBeTruthy();
  expect(screen.queryByText(/503/)).toBeNull();
  // A failed income list can't tell whether onboarding is needed, so the app opens.
  expect(screen).toHavePathname('/');

  await press('Try again');

  expect(await screen.findByText('Acme payroll')).toBeTruthy();
  await waitFor(() =>
    expect(
      screen.queryByText('Something went wrong on our side. Try again in a moment.'),
    ).toBeNull(),
  );
});
