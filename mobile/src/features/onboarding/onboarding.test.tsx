import { screen, waitFor } from 'expo-router/testing-library';

import { EMAIL, launch, press, settle, setUp, type } from '@/test/app';
import type { FakeBackend } from '@/test/fakeBackend';
import { todayLocal } from '@/lib/dates';

jest.mock('@/api/config', () => ({ API_BASE_URL: 'http://api.test' }));
jest.mock('expo-secure-store', () => jest.requireActual('@/test/fakeSecureStore'));
jest.mock('expo-splash-screen', () => jest.requireActual('@/test/app').splashScreenMock);
jest.mock('@/api/queryClient', () => jest.requireActual('@/test/app').queryClientMock());

let backend: FakeBackend;

afterEach(settle);

beforeEach(async () => {
  backend = await setUp({ withIncome: false });
});

/** Step 1, filled in validly: a biweekly paycheck whose payday is today. */
async function fillIncome() {
  await type('Name', 'Acme payroll');
  await type('Take-home pay per paycheck', '1500.29');
  await press(/^A payday:/);
  await press('Today');
}

it('walks through income, balance and the suggested goal, then lands on Home', async () => {
  await launch();
  expect(await screen.findByText('When do you get paid?')).toBeTruthy();
  expect(screen.getByText('Step 1 of 3')).toBeTruthy();

  await fillIncome();
  await press('Continue');

  // Creating the income refetched the list, but onboarding carries on.
  expect(await screen.findByText('How much do you have right now?')).toBeTruthy();
  expect(screen).toHavePathname('/onboarding');
  await type('Available balance', '812.29');
  await press('Continue');

  expect(await screen.findByText('Start an emergency fund')).toBeTruthy();
  expect(screen.getByLabelText('Target').props.value).toBe('1000.00');
  await type('Target', '1500');
  await press('Save goal');

  expect(await screen.findByText('$812.29')).toBeTruthy();
  expect(screen).toHavePathname('/');
  expect(screen.getByText('Emergency fund')).toBeTruthy();
  expect(backend.lastBody('POST /income-sources')).toEqual({
    name: 'Acme payroll',
    expected_amount_cents: 150029,
    schedule: { type: 'biweekly', anchor_date: todayLocal() },
  });
  expect(backend.lastBody('POST /balance-snapshots')).toEqual({ amount_cents: 81229 });
  expect(backend.lastBody('POST /goals')).toEqual({
    name: 'Emergency fund',
    kind: 'emergency',
    target_cents: 150000,
    current_cents: 0,
    priority: 1,
    deadline: null,
  });
});

it('lets the balance and the goal be skipped, and Home asks for a balance', async () => {
  await launch();
  await screen.findByText('When do you get paid?');
  await fillIncome();
  await press('Continue');

  await screen.findByText('How much do you have right now?');
  await press('Skip for now');
  await screen.findByText('Start an emergency fund');
  await press('Skip');

  expect(
    await screen.findByText('No balance yet. Your plan starts from $0 until you add one.'),
  ).toBeTruthy();
  expect(screen.getByText('No goals yet.')).toBeTruthy();
  expect(backend.count('POST /balance-snapshots')).toBe(0);
  expect(backend.count('POST /goals')).toBe(0);
});

it('shows a 422 next to the field it names, and stays on the step', async () => {
  await launch();
  await screen.findByText('When do you get paid?');
  await fillIncome();
  await type('Name', '   ');

  await press('Continue');

  expect(
    await screen.findByLabelText('Name: String should have at least 1 character'),
  ).toBeTruthy();
  expect(screen.getByText('Check the fields marked above.')).toBeTruthy();
  expect(screen.getByText('Step 1 of 3')).toBeTruthy();
});

it('catches an amount it can’t read before sending anything', async () => {
  await launch();
  await screen.findByText('When do you get paid?');
  await fillIncome();
  await type('Take-home pay per paycheck', '1,500');

  await press('Continue');

  expect(
    screen.getByLabelText(
      'Take-home pay per paycheck: Use digits and an optional point, like 1250.50.',
    ),
  ).toBeTruthy();
  expect(backend.count('POST /income-sources')).toBe(0);
});

it('shows a friendly message when the server fails, and can try again', async () => {
  backend.failNext('POST /income-sources', 500);
  await launch();
  await screen.findByText('When do you get paid?');
  await fillIncome();

  await press('Continue');

  expect(
    await screen.findByText('Something went wrong on our side. Try again in a moment.'),
  ).toBeTruthy();
  expect(screen.queryByText(/status 500/)).toBeNull();
  await press('Continue');
  expect(await screen.findByText('How much do you have right now?')).toBeTruthy();
});

const EMERGENCY = {
  name: 'Rainy day',
  kind: 'emergency',
  target_cents: 50000,
  current_cents: 0,
  priority: 1,
  deadline: null,
};

it('skips the goal step when an emergency goal already exists', async () => {
  backend.seed(EMAIL, '/goals', EMERGENCY);
  await launch();
  await screen.findByText('When do you get paid?');
  expect(screen.getByText('Step 1 of 2')).toBeTruthy();
  await fillIncome();
  await press('Continue');
  await screen.findByText('How much do you have right now?');
  expect(screen.getByText('Step 2 of 2')).toBeTruthy();

  await press('Skip for now');

  expect(await screen.findByText('Rainy day')).toBeTruthy();
  expect(screen).toHavePathname('/');
  expect(screen.queryByText('Start an emergency fund')).toBeNull();
  expect(backend.count('POST /goals')).toBe(0);
});

it('skips the balance step when a balance already exists, keeping the step numbers', async () => {
  backend.seed(EMAIL, '/balance-snapshots', { amount_cents: 81229 });
  await launch();
  await screen.findByText('When do you get paid?');
  expect(screen.getByText('Step 1 of 2')).toBeTruthy();
  await fillIncome();

  await press('Continue');

  expect(await screen.findByText('Start an emergency fund')).toBeTruthy();
  expect(screen.getByText('Step 2 of 2')).toBeTruthy();
  expect(screen.queryByText('How much do you have right now?')).toBeNull();
});

it('only asks for income after the only income was removed, then opens the app', async () => {
  // As after archiving the only income source: the balance and goal are still there.
  backend.seed(EMAIL, '/balance-snapshots', { amount_cents: 81229 });
  backend.seed(EMAIL, '/goals', EMERGENCY);
  await launch();
  await screen.findByText('When do you get paid?');
  expect(screen.getByText('Step 1 of 1')).toBeTruthy();
  await fillIncome();

  await press('Continue');

  expect(await screen.findByText('$812.29')).toBeTruthy();
  expect(screen).toHavePathname('/');
  expect(screen.getByText('Rainy day')).toBeTruthy();
  expect(backend.count('POST /goals')).toBe(0);
  expect(backend.count('POST /balance-snapshots')).toBe(0);
});

it('keeps the goal step when goals can’t be loaded, and a duplicate is still refused', async () => {
  backend.seed(EMAIL, '/goals', EMERGENCY);
  backend.failNext('GET /goals', 503, { times: Infinity }); // never loads
  await launch();
  await screen.findByText('When do you get paid?');
  expect(screen.getByText('Step 1 of 3')).toBeTruthy();
  await fillIncome();
  await press('Continue');
  await screen.findByText('How much do you have right now?');
  await press('Skip for now');
  await screen.findByText('Start an emergency fund');

  await press('Save goal');

  expect(
    await screen.findByText('You already have an emergency fund goal. Change that one instead.'),
  ).toBeTruthy();
  await press('Skip');
  await waitFor(() => expect(screen).toHavePathname('/'));
  expect(backend.items(EMAIL, '/goals')).toHaveLength(1);
});

it('is skipped for an account that already has income', async () => {
  backend = await setUp({ withIncome: true });

  await launch();

  expect(await screen.findByText('Acme payroll')).toBeTruthy();
  await waitFor(() => expect(screen.queryByTestId('deciding-cover')).toBeNull());
  expect(screen).toHavePathname('/');
  expect(screen.queryByText('When do you get paid?')).toBeNull();
});
