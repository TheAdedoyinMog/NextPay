/**
 * The bill, essential, debt and goal screens, from Home: what is typed becomes the exact
 * request (cents, basis points, explicit nulls), 422s land on their fields, and deletes ask.
 */
import { screen } from 'expo-router/testing-library';
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

async function open(section: string, addLabel: string) {
  await launch();
  await openFromHome(section);
  await screen.findByRole('button', { name: addLabel });
}

/** Presses the destructive button of the confirmation that `trigger` opens. */
async function confirmThrough(trigger: string) {
  const alert = jest.spyOn(Alert, 'alert');
  await press(trigger);
  const buttons = alert.mock.calls.at(-1)?.[2] ?? [];
  buttons.find((button) => button.style === 'destructive')?.onPress?.();
}

describe('bills', () => {
  const RENT = {
    name: 'Rent',
    amount_cents: 120000,
    priority: 1,
    first_due_date: '2026-12-01',
    repeat_every_months: 1,
  };

  it('adds a bill with its due date as a calendar date', async () => {
    await open('bills', 'Add bill');
    expect(screen.getByText('No bills yet')).toBeTruthy();
    await press('Add bill');

    await type('Name', 'Phone');
    await type('Amount', '45.99');
    await press(/^Next due:/);
    await press('Next month');
    await press('Next month');
    // Whatever month that is, its first day, chosen by its label, never through a Date.
    const firstOfMonth = screen
      .getAllByRole('button')
      .find((b) => / 1, \d{4}$/.test(b.props.accessibilityLabel ?? ''));
    await press(firstOfMonth?.props.accessibilityLabel);
    await choose('Repeats', 'Every 3 months');
    await press('Add bill');

    expect(await screen.findByText('Phone')).toBeTruthy();
    const sent = backend.lastBody('POST /bills') as Record<string, unknown>;
    expect(sent).toMatchObject({
      name: 'Phone',
      amount_cents: 4599,
      priority: 1,
      repeat_every_months: 3,
    });
    expect(sent.first_due_date).toMatch(/^\d{4}-\d{2}-01$/);
  });

  it('makes a bill one-off by sending repeat_every_months: null', async () => {
    const rent = backend.seed(EMAIL, '/bills', RENT);
    await open('bills', 'Add bill');
    await press('Rent');

    expect(screen.getByRole('button', { name: 'Next due: Dec 1, 2026' })).toBeTruthy();
    await choose('Repeats', 'Just once');
    await press('Save changes');

    expect(await screen.findByText('Once, on Dec 1, 2026')).toBeTruthy();
    expect(backend.lastBody(`PUT /bills/${rent.id}`)).toEqual({
      ...RENT,
      repeat_every_months: null,
    });
  });

  it('keeps an unusual interval when editing other fields', async () => {
    const rent = backend.seed(EMAIL, '/bills', { ...RENT, repeat_every_months: 2 });
    await open('bills', 'Add bill');
    await press('Rent');

    expect(screen.getByRole('button', { name: 'Repeats: Every 2 months' })).toBeTruthy();
    await type('Amount', '1250');
    await press('Save changes');

    await screen.findByText('$1,250.00');
    expect(backend.lastBody(`PUT /bills/${rent.id}`)).toMatchObject({
      repeat_every_months: 2,
      amount_cents: 125000,
    });
  });

  it('shows a 422 next to its field', async () => {
    backend.seed(EMAIL, '/bills', RENT);
    await open('bills', 'Add bill');
    await press('Rent');
    await type('Priority', '0');

    await press('Save changes');

    expect(await screen.findByLabelText('Priority: Input should be greater than 0')).toBeTruthy();
  });

  it('deletes after confirming', async () => {
    backend.seed(EMAIL, '/bills', RENT);
    await open('bills', 'Add bill');
    await press('Rent');

    await confirmThrough('Delete bill');

    expect(await screen.findByText('No bills yet')).toBeTruthy();
  });
});

describe('essentials', () => {
  it('adds, edits and deletes one', async () => {
    await open('essentials', 'Add essential');
    await press('Add essential');
    await type('Name', 'Groceries');
    await type('Amount per pay period', '150');
    await press('Add essential');

    expect(await screen.findByText('Groceries')).toBeTruthy();
    expect(backend.lastBody('POST /essential-expenses')).toEqual({
      name: 'Groceries',
      amount_per_period_cents: 15000,
    });

    await press('Groceries');
    expect(screen.getByLabelText('Amount per pay period').props.value).toBe('150.00');
    await type('Amount per pay period', '19.99');
    await press('Save changes');
    expect(await screen.findByText('$19.99')).toBeTruthy();

    await press('Groceries');
    await confirmThrough('Delete essential');
    expect(await screen.findByText('No essentials yet')).toBeTruthy();
  });
});

describe('debts', () => {
  const VISA = {
    name: 'Visa',
    balance_cents: 250000,
    apr_bps: 2499,
    minimum_payment_cents: 3500,
    due_day: 15,
  };

  it('adds a debt, turning the percent into basis points by its digits', async () => {
    await open('debts', 'Add debt');
    await press('Add debt');
    await type('Name', 'Car loan');
    await type('Balance owed', '8000');
    await type('Interest rate (APR)', '6.9');
    await type('Minimum payment', '210.29');
    await type('Due day of the month', '3');
    await press('Add debt');

    expect(await screen.findByText('Car loan')).toBeTruthy();
    expect(screen.getByText('6.90% APR · $210.29 minimum · due the 3rd')).toBeTruthy();
    expect(backend.lastBody('POST /debts')).toEqual({
      name: 'Car loan',
      balance_cents: 800000,
      apr_bps: 690,
      minimum_payment_cents: 21029,
      due_day: 3,
    });
  });

  it('shows the stored rate as a percent when editing, and rejects three decimals', async () => {
    backend.seed(EMAIL, '/debts', VISA);
    await open('debts', 'Add debt');
    await press('Visa');

    expect(screen.getByLabelText('Interest rate (APR)').props.value).toBe('24.99');
    await type('Interest rate (APR)', '24.999');
    await press('Save changes');

    expect(
      screen.getByLabelText(
        'Interest rate (APR): Enter the rate as a percent with up to two decimals, like 24.99.',
      ),
    ).toBeTruthy();
    expect(backend.count('PUT /debts/' + backend.items(EMAIL, '/debts')[0]?.id)).toBe(0);
  });

  it('deletes after confirming', async () => {
    backend.seed(EMAIL, '/debts', VISA);
    await open('debts', 'Add debt');
    await press('Visa');

    await confirmThrough('Delete debt');

    expect(await screen.findByText('No debts yet')).toBeTruthy();
  });
});

describe('goals', () => {
  const CAMERA = {
    name: 'Camera',
    kind: 'purchase',
    target_cents: 89999,
    current_cents: 10000,
    priority: 2,
    deadline: '2027-03-01',
  };

  it('adds a purchase goal with no deadline, sent as null', async () => {
    await open('goals', 'Add goal');
    await press('Add goal');
    await type('Name', 'Bike');
    await choose('Kind', 'Something to buy');
    await type('Target', '650');
    await press('Add goal');

    expect(await screen.findByText('Bike')).toBeTruthy();
    expect(backend.lastBody('POST /goals')).toEqual({
      name: 'Bike',
      kind: 'purchase',
      target_cents: 65000,
      current_cents: 0,
      priority: 1,
      deadline: null,
    });
  });

  it('clears a deadline on edit by sending null', async () => {
    const camera = backend.seed(EMAIL, '/goals', CAMERA);
    await open('goals', 'Add goal');
    await press('Camera');

    await press('Deadline: Mar 1, 2027');
    await press('No deadline');
    await press('Save changes');

    expect(await screen.findByText('Something to buy · $100.00 saved')).toBeTruthy();
    expect(backend.lastBody(`PUT /goals/${camera.id}`)).toEqual({ ...CAMERA, deadline: null });
  });

  it('explains a second emergency fund', async () => {
    backend.seed(EMAIL, '/goals', { ...CAMERA, name: 'Emergency fund', kind: 'emergency' });
    await open('goals', 'Add goal');
    await press('Add goal');
    await type('Name', 'Another');
    await choose('Kind', 'Emergency fund');
    await type('Target', '500');

    await press('Add goal');

    expect(
      await screen.findByText('You already have an emergency fund goal. Change that one instead.'),
    ).toBeTruthy();
  });

  it('deletes after confirming', async () => {
    backend.seed(EMAIL, '/goals', CAMERA);
    await open('goals', 'Add goal');
    await press('Camera');

    await confirmThrough('Delete goal');

    expect(await screen.findByText('No goals yet')).toBeTruthy();
  });
});

describe('balance', () => {
  it('updates the balance from Home, keeps the old one as history, and allows overdrawn', async () => {
    backend.seed(EMAIL, '/balance-snapshots', { amount_cents: 81229 });
    await launch();
    await screen.findByRole('button', { name: 'Update balance' });
    await press('Update balance');

    expect(await screen.findByText('$812.29')).toBeTruthy();
    await type('Available balance', '-40.5');
    await press('Save balance');

    expect(await screen.findByText('-$40.50')).toBeTruthy();
    expect(screen.getByText('Earlier')).toBeTruthy();
    expect(backend.lastBody('POST /balance-snapshots')).toEqual({ amount_cents: -4050 });
    // The form is cleared for the next update.
    expect(screen.getByLabelText('Available balance').props.value).toBe('');
  });
});

describe('the Setup tab', () => {
  it('counts what is set up and opens each list', async () => {
    backend.seed(EMAIL, '/goals', {
      name: 'Camera',
      kind: 'purchase',
      target_cents: 1000,
      current_cents: 0,
      priority: 1,
      deadline: null,
    });
    await launch();
    await press(/^Setup, tab/);

    expect(await screen.findByText('Not set')).toBeTruthy(); // no balance yet
    await press('Goals');
    expect(await screen.findByText('Camera')).toBeTruthy();
    expect(screen).toHavePathname('/setup/goals');
  });
});
