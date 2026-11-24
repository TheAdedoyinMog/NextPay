/**
 * The payday loop through the whole app: dashboard, recording the paycheck, the plan,
 * committing, marking paid, undoing a payment, out-of-date plans, and repeated requests
 * (ADR 0015, ADR 0017).
 */
import { router } from 'expo-router';
import { act, fireEvent, screen, waitFor } from 'expo-router/testing-library';
import { Alert } from 'react-native';

import { EMAIL, launch, press, settle, setUp, setupChangedElsewhere, type } from '@/test/app';
import type { FakeBackend } from '@/test/fakeBackend';

jest.mock('@/api/config', () => ({ API_BASE_URL: 'http://api.test' }));
jest.mock('expo-secure-store', () => jest.requireActual('@/test/fakeSecureStore'));
jest.mock('expo-splash-screen', () => jest.requireActual('@/test/app').splashScreenMock);
jest.mock('@/api/queryClient', () => jest.requireActual('@/test/app').queryClientMock());

const RENT_EXPLANATION = 'Rent is $800.00, due Dec 1. Half of it comes from this paycheck.';

let backend: FakeBackend;
let ids: { job: string; rent: string; car: string; fund: string };

beforeEach(async () => {
  backend = await setUp({ withIncome: true });
  const job = backend.items(EMAIL, '/income-sources')[0]?.id ?? '';
  const rent = backend.seed(EMAIL, '/bills', {
    name: 'Rent',
    amount_cents: 80000,
    priority: 1,
    first_due_date: '2026-12-01',
    repeat_every_months: 1,
  });
  const groceries = backend.seed(EMAIL, '/essential-expenses', {
    name: 'Groceries',
    amount_per_period_cents: 20000,
  });
  const car = backend.seed(EMAIL, '/debts', {
    name: 'Car loan',
    balance_cents: 500000,
    apr_bps: 690,
    minimum_payment_cents: 15000,
    due_day: 20,
  });
  const fund = backend.seed(EMAIL, '/goals', {
    name: 'Emergency fund',
    kind: 'emergency',
    target_cents: 100000,
    current_cents: 0,
    priority: 1,
    deadline: null,
  });
  backend.seed(EMAIL, '/balance-snapshots', { amount_cents: 81229 });
  backend.planning.setPaydays(EMAIL, {
    current: {
      income_source_id: job,
      income_source_name: 'Acme payroll',
      pay_date: '2026-11-20',
      expected_amount_cents: 150000,
    },
    next: {
      income_source_id: job,
      income_source_name: 'Acme payroll',
      pay_date: '2026-12-04',
      expected_amount_cents: 150000,
    },
  });
  backend.planning.template = {
    safe_to_spend_cents: 75833,
    summary: 'Safe to Spend is $758.33: what’s left after everything above.',
    allocations: [
      {
        tier: 'bill',
        name: 'Rent',
        target_id: rent.id,
        funded_cents: 40000,
        due_date: '2026-12-01',
        explanation: RENT_EXPLANATION,
      },
      { tier: 'essential', name: 'Groceries', target_id: groceries.id, funded_cents: 20000 },
      {
        tier: 'debt_minimum',
        name: 'Car loan',
        target_id: car.id,
        funded_cents: 15000,
        due_date: '2026-12-20',
      },
      {
        tier: 'emergency_fund',
        name: 'Emergency fund',
        target_id: fund.id,
        requested_cents: 10000,
        funded_cents: 5000,
        shortfall_cents: 5000,
      },
    ],
  };
  ids = { job, rent: rent.id, car: car.id, fund: fund.id };
});

afterEach(async () => {
  jest.restoreAllMocks();
  await settle();
});

/** Records the destructive button of every confirmation, to press it once or twice. */
function captureConfirmations() {
  const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
  return () => {
    const buttons = alert.mock.calls.at(-1)?.[2] ?? [];
    const confirm = buttons.find((button) => button.style === 'destructive');
    if (!confirm?.onPress) throw new Error('no confirmation was shown');
    return confirm.onPress;
  };
}

/** From Home, through the payday flow to the draft plan. */
async function makeDraft() {
  await launch();
  await fireEvent.press(await screen.findByRole('button', { name: 'Plan this paycheck' }));
  await screen.findByText('What did this paycheck pay?');
  await press('Continue');
  await screen.findByText('Your balance before this paycheck');
  await press('Make my plan');
  await screen.findByText('Safe to Spend after you commit');
}

async function commitDraft() {
  const confirmation = captureConfirmations();
  await press('Commit plan');
  confirmation()();
  await screen.findByText(/^Committed /);
}

describe('the dashboard', () => {
  it('shows the paycheck to plan, the next payday and the balance, before any plan', async () => {
    await launch();

    expect(
      await screen.findByText('Commit a plan for your paycheck to see what’s safe to spend.'),
    ).toBeTruthy();
    expect(screen.getByText('Payday · Nov 20, 2026')).toBeTruthy();
    expect(screen.getByText('Acme payroll · $1,500.00')).toBeTruthy();
    expect(screen.getByText('No plan yet.')).toBeTruthy();
    expect(screen.getByText('Next payday: Dec 4, 2026 (Acme payroll)')).toBeTruthy();
    expect(screen.getAllByText('$812.29').length).toBeGreaterThan(0);
  });

  it('shows any shortfall separately from Safe to Spend, on the plan and on Home', async () => {
    backend.planning.template = {
      ...backend.planning.template!,
      safe_to_spend_cents: 0,
      reserve_deficit_cents: 2500,
    };
    await makeDraft();
    await commitDraft();

    expect(screen.getByText(/^Shortfall: \$25\.00\. More is set aside than you have/)).toBeTruthy();
    await act(() => router.back());

    expect(
      await screen.findByText('Shortfall: $25.00. More is set aside or paid than you have.'),
    ).toBeTruthy();
    expect(screen.getByText('$0.00')).toBeTruthy();
  });

  it('shows a friendly error with a retry', async () => {
    // Already in the phone's zone, so no settings change refreshes the dashboard meanwhile.
    backend.setSettings(EMAIL, {
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      no_deadline_goal_share_bps: 2000,
    });
    backend.failNext('GET /dashboard', 500, { times: 2 });
    await launch();

    expect(
      await screen.findByText('Something went wrong on our side. Try again in a moment.'),
    ).toBeTruthy();
    await press('Try again');
    expect(await screen.findByText('No plan yet.')).toBeTruthy();
  });
});

describe('recording the paycheck and planning it', () => {
  it('records what arrived, asks for the balance before it, and shows the plan as the API wrote it', async () => {
    await launch();
    await fireEvent.press(await screen.findByRole('button', { name: 'Plan this paycheck' }));

    expect(screen.getByLabelText('Amount that arrived').props.value).toBe('1500.00');
    await type('Amount that arrived', '1450.29');
    await press('Continue');
    expect(await screen.findByText('Your balance before this paycheck')).toBeTruthy();
    expect(screen.getByLabelText('Balance before this paycheck').props.value).toBe('812.29');
    await type('Balance before this paycheck', '700');
    await press('Make my plan');

    expect(await screen.findByText('Safe to Spend after you commit')).toBeTruthy();
    expect(screen.getByText('$758.33')).toBeTruthy();
    expect(
      screen.getByText('Safe to Spend is $758.33: what’s left after everything above.'),
    ).toBeTruthy();
    expect(screen.getByText(RENT_EXPLANATION)).toBeTruthy();
    expect(screen.getByText('Short by $50.00')).toBeTruthy();
    for (const title of ['Bills', 'Essentials', 'Debt payments', 'Emergency fund']) {
      expect(screen.getAllByText(title).length).toBeGreaterThan(0);
    }
    expect(backend.lastBody(`PUT /income-sources/${ids.job}/paychecks/2026-11-20`)).toEqual({
      actual_amount_cents: 145029,
    });
    expect(backend.lastBody('POST /balance-snapshots')).toEqual({ amount_cents: 70000 });
    expect(screen.queryByRole('button', { name: /^Mark .* paid$/ })).toBeNull(); // only once committed
  });

  it('catches an amount it can’t read before sending', async () => {
    await launch();
    await fireEvent.press(await screen.findByRole('button', { name: 'Plan this paycheck' }));
    await type('Amount that arrived', '1,450');

    await press('Continue');

    expect(
      screen.getByLabelText('Amount that arrived: Use digits and an optional point, like 1250.50.'),
    ).toBeTruthy();
    expect(backend.calls.some((call) => call.includes('/paychecks/'))).toBe(false);
  });

  it('shows a friendly message if planning fails, and tries again', async () => {
    backend.failNext('POST /plans', 503);
    await launch();
    await fireEvent.press(await screen.findByRole('button', { name: 'Plan this paycheck' }));
    await press('Continue');
    await screen.findByText('Your balance before this paycheck');
    await press('Make my plan');

    expect(
      await screen.findByText('Something went wrong on our side. Try again in a moment.'),
    ).toBeTruthy();
    await press('Try again');
    expect(await screen.findByText('Safe to Spend after you commit')).toBeTruthy();
  });
});

describe('committing', () => {
  it('asks first, then sets money aside and shows Safe to Spend on Home', async () => {
    await makeDraft();
    const confirmation = captureConfirmations();
    await press('Commit plan');
    expect(jest.mocked(Alert.alert).mock.calls[0]?.[1]).toMatch(
      /set aside, so it no longer counts as safe to spend/,
    );
    expect(backend.count('POST /plans/plan-1/commit')).toBe(0);

    confirmation()();

    expect(await screen.findByText(/^Committed /)).toBeTruthy();
    expect(screen.getByText('Safe to Spend when committed')).toBeTruthy();
    expect(backend.items(EMAIL, '/bills')[0]?.reserved_cents).toBe(40000);
    expect(await screen.findByText('Set aside now: $400.00')).toBeTruthy(); // Rent
  });

  it('sets money aside once when Commit is confirmed twice', async () => {
    await makeDraft();
    const confirmation = captureConfirmations();
    await press('Commit plan');

    const commit = confirmation();
    commit();
    commit();

    await screen.findByText(/^Committed /);
    expect(backend.items(EMAIL, '/bills')[0]?.reserved_cents).toBe(40000);
    expect(backend.items(EMAIL, '/goals')[0]?.current_cents).toBe(5000);
  });

  it('sets money aside once when the commit went through but its reply was lost', async () => {
    await makeDraft();
    backend.loseResponseNext('POST /plans/plan-1/commit');
    const confirmation = captureConfirmations();
    await press('Commit plan');
    confirmation()();

    expect(await screen.findByText('Could not reach the server at http://api.test.')).toBeTruthy();
    await press('Commit plan'); // after a failure, this retries straight away

    expect(await screen.findByText(/^Committed /)).toBeTruthy();
    expect(backend.count('POST /plans/plan-1/commit')).toBe(2);
    expect(backend.items(EMAIL, '/bills')[0]?.reserved_cents).toBe(40000);
  });

  it('makes the plan again when commit says it is out of date, and says why', async () => {
    await makeDraft();
    backend.planning.bump(EMAIL); // a change on another device, after this screen loaded
    const confirmation = captureConfirmations();
    await press('Commit plan');
    confirmation()();

    expect(
      await screen.findByText(
        'Your details changed, so the plan was updated. Review it, then commit.',
      ),
    ).toBeTruthy();
    expect(screen).toHavePathname('/plan/plan-2');
    expect(screen.queryByText(/Generate a new plan/)).toBeNull(); // never shown as a failure
  });
});

describe('out-of-date plans', () => {
  it('warns on Home and plans the paycheck again from the start', async () => {
    backend.planning.handle(
      'POST',
      '/plans',
      { income_source_id: ids.job, pay_date: '2026-11-20' },
      EMAIL,
    );
    backend.planning.bump(EMAIL); // for example, a bill was edited
    await launch();

    expect(await screen.findByText('Your details changed since this plan was made.')).toBeTruthy();
    await press('Update the plan');
    expect(await screen.findByText('What did this paycheck pay?')).toBeTruthy();
    await press('Continue');
    await screen.findByText('Your balance before this paycheck');
    await press('Make my plan');

    expect(await screen.findByText('Safe to Spend after you commit')).toBeTruthy();
    expect(screen).toHavePathname('/plan/plan-2');
    expect(screen.queryByText(/Update it before committing/)).toBeNull();
  });

  it('shows a banner on an open plan when setup changes, and replaces the draft', async () => {
    await makeDraft();
    backend.planning.bump(EMAIL);

    await setupChangedElsewhere();

    expect(
      await screen.findByText(
        'Your details changed since this plan was made. Update it before committing.',
      ),
    ).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Commit plan' })).toBeNull();
    await press('Update the plan');
    expect(
      await screen.findByText(
        'Your details changed, so the plan was updated. Review it, then commit.',
      ),
    ).toBeTruthy();
    expect(screen).toHavePathname('/plan/plan-2');
    expect(screen.getByRole('button', { name: 'Commit plan' })).toBeTruthy();
  });
});

describe('marking paid', () => {
  it('draws the reserve down once when Mark paid is confirmed twice', async () => {
    await makeDraft();
    await commitDraft();
    const confirmation = captureConfirmations();
    await fireEvent.press(await screen.findByRole('button', { name: 'Mark Rent paid' }));
    expect(jest.mocked(Alert.alert).mock.calls.at(-1)?.[1]).toBe(
      'Records $800.00 paid today for the Dec 1, 2026 bill. You can undo it until your next plan is committed.',
    );

    const pay = confirmation();
    pay();
    pay();

    expect(await screen.findByText('✓ Paid $800.00 on Nov 20, 2026')).toBeTruthy();
    const bodies = backend.bodies.filter((b) => b.call === `POST /bills/${ids.rent}/payments`);
    expect(new Set(bodies.map((b) => (b.body as { id: string }).id)).size).toBe(1);
    expect(backend.items(EMAIL, '/bills')[0]?.reserved_cents).toBe(0); // 400 set aside, 800 paid
    expect(screen.getByText('Set aside now: $0.00')).toBeTruthy();
  });

  it('records one bill payment when the first reply was lost and the user retries', async () => {
    await makeDraft();
    await commitDraft();
    backend.loseResponseNext(`POST /bills/${ids.rent}/payments`);
    const confirmation = captureConfirmations();
    await fireEvent.press(await screen.findByRole('button', { name: 'Mark Rent paid' }));
    confirmation()();

    await fireEvent.press(await screen.findByRole('button', { name: 'Try paying Rent again' }));

    expect(await screen.findByText('✓ Paid $800.00 on Nov 20, 2026')).toBeTruthy();
    const bodies = backend.bodies.filter((b) => b.call === `POST /bills/${ids.rent}/payments`);
    expect(bodies).toHaveLength(2);
    expect(bodies[0]?.body).toEqual(bodies[1]?.body); // the same id both times
    expect(backend.items(EMAIL, '/bills')[0]?.reserved_cents).toBe(0);
  });

  it('records one debt payment for a double tap and for a lost reply', async () => {
    await makeDraft();
    await commitDraft();
    backend.loseResponseNext(`POST /debts/${ids.car}/payments`);
    const confirmation = captureConfirmations();
    await fireEvent.press(await screen.findByRole('button', { name: 'Mark Car loan paid' }));
    const pay = confirmation();
    pay();
    pay();
    await fireEvent.press(await screen.findByRole('button', { name: /Car loan/ }));

    expect(await screen.findByText('✓ Paid $150.00 on Nov 20, 2026')).toBeTruthy();
    expect(backend.items(EMAIL, '/debts')[0]?.balance_cents).toBe(485000);
  });

  it('pays the minimum its line names, so the next plan knows it is paid (ADR 0018)', async () => {
    await makeDraft();
    await commitDraft();
    const confirmation = captureConfirmations();
    await fireEvent.press(await screen.findByRole('button', { name: 'Mark Car loan paid' }));
    expect(jest.mocked(Alert.alert).mock.calls.at(-1)?.[1]).toContain(
      'for the one due Dec 20, 2026',
    );
    confirmation()();

    expect(await screen.findByText('✓ Paid $150.00 on Nov 20, 2026')).toBeTruthy();
    const [sent] = backend.bodies.filter((b) => b.call === `POST /debts/${ids.car}/payments`);
    expect(sent?.body).toMatchObject({ due_date: '2026-12-20' });
  });
});

describe('Safe to Spend on Home after paying', () => {
  it('stays the same for a payment its reserve covered', async () => {
    await makeDraft();
    await commitDraft();
    const confirmation = captureConfirmations();
    await fireEvent.press(await screen.findByRole('button', { name: 'Mark Car loan paid' }));
    confirmation()(); // $150 set aside, $150 paid
    await screen.findByText('✓ Paid $150.00 on Nov 20, 2026');

    await act(() => router.back());

    expect(await screen.findByText('$758.33')).toBeTruthy();
    expect(screen.queryByText(/beyond what was set/)).toBeNull();
  });

  it('falls by what was paid beyond the reserve, as the API says', async () => {
    await makeDraft();
    await commitDraft();
    const confirmation = captureConfirmations();
    await fireEvent.press(await screen.findByRole('button', { name: 'Mark Rent paid' }));
    confirmation()(); // $400 set aside, $800 paid
    await screen.findByText('✓ Paid $800.00 on Nov 20, 2026');

    await act(() => router.back());

    expect(await screen.findByText('$358.33')).toBeTruthy();
    expect(screen.getByText('Includes $400.00 you paid beyond what was set aside.')).toBeTruthy();
  });
});

describe('the time zone', () => {
  it('follows the phone, once', async () => {
    await launch();
    await waitFor(() => expect(backend.count('PUT /me/settings')).toBe(1));

    expect(backend.lastBody('PUT /me/settings')).toEqual({
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      no_deadline_goal_share_bps: 2000,
    });
    await screen.findByText('No plan yet.');
    expect(backend.count('PUT /me/settings')).toBe(1);
  });
});

describe('undoing a payment', () => {
  /** On the committed plan: marks Rent paid ($400 set aside, $800 paid) and returns its id. */
  async function payRent(): Promise<string> {
    const confirmation = captureConfirmations();
    await fireEvent.press(await screen.findByRole('button', { name: 'Mark Rent paid' }));
    confirmation()();
    await screen.findByText('✓ Paid $800.00 on Nov 20, 2026');
    return (backend.lastBody(`POST /bills/${ids.rent}/payments`) as { id: string }).id;
  }

  it('puts the reserve and Safe to Spend on Home back, after asking', async () => {
    await makeDraft();
    await commitDraft();
    await payRent();
    expect(screen.getByText('Set aside now: $0.00')).toBeTruthy();
    const confirmation = captureConfirmations();

    await fireEvent.press(screen.getByRole('button', { name: 'Undo the Rent payment' }));
    expect(jest.mocked(Alert.alert).mock.calls.at(-1)?.slice(0, 2)).toEqual([
      'Undo the Rent payment?',
      'Removes the $800.00 payment from Nov 20, 2026 and puts back what it took from the money set aside. Safe to Spend on Home updates. You can mark it paid again.',
    ]);
    confirmation()();

    expect(await screen.findByRole('button', { name: 'Mark Rent paid' })).toBeTruthy();
    expect(screen.getByText('Set aside now: $400.00')).toBeTruthy();
    expect(backend.items(EMAIL, '/bills')[0]?.reserved_cents).toBe(40000);
    await act(() => router.back());
    expect(await screen.findByText('$758.33')).toBeTruthy();
    expect(screen.queryByText(/beyond what was set/)).toBeNull();
  });

  it('undoes once when Undo is confirmed twice', async () => {
    await makeDraft();
    await commitDraft();
    const paymentId = await payRent();
    const confirmation = captureConfirmations();
    await fireEvent.press(screen.getByRole('button', { name: 'Undo the Rent payment' }));

    const undo = confirmation();
    undo();
    undo();

    expect(await screen.findByRole('button', { name: 'Mark Rent paid' })).toBeTruthy();
    expect(backend.count(`POST /bills/${ids.rent}/payments/${paymentId}/undo`)).toBeGreaterThan(0);
    expect(backend.items(EMAIL, '/bills')[0]?.reserved_cents).toBe(40000);
  });

  it('undoes once when the first reply was lost and the user retries', async () => {
    await makeDraft();
    await commitDraft();
    const paymentId = await payRent();
    const call = `POST /bills/${ids.rent}/payments/${paymentId}/undo`;
    backend.loseResponseNext(call);
    const confirmation = captureConfirmations();
    await fireEvent.press(screen.getByRole('button', { name: 'Undo the Rent payment' }));
    confirmation()();

    await fireEvent.press(
      await screen.findByRole('button', { name: 'Try undoing the Rent payment again' }),
    );

    expect(await screen.findByRole('button', { name: 'Mark Rent paid' })).toBeTruthy();
    expect(backend.count(call)).toBe(2);
    expect(backend.items(EMAIL, '/bills')[0]?.reserved_cents).toBe(40000);
  });

  it('records paying again as a new payment', async () => {
    await makeDraft();
    await commitDraft();
    const first = await payRent();
    const undoConfirmation = captureConfirmations();
    await fireEvent.press(screen.getByRole('button', { name: 'Undo the Rent payment' }));
    undoConfirmation()();
    await screen.findByRole('button', { name: 'Mark Rent paid' });

    const second = await payRent();

    expect(second).not.toBe(first);
    expect(backend.items(EMAIL, '/bills')[0]?.reserved_cents).toBe(0);
    await act(() => router.back());
    expect(await screen.findByText('$358.33')).toBeTruthy();
  });

  it('is replaced by a hint once a later plan was committed', async () => {
    await makeDraft();
    await commitDraft();
    await payRent();
    const confirmation = captureConfirmations();
    await fireEvent.press(screen.getByRole('button', { name: 'Mark Car loan paid' }));
    confirmation()();
    await screen.findByRole('button', { name: 'Undo the Car loan payment' });
    expect(screen.getByRole('button', { name: 'Undo the Rent payment' })).toBeTruthy();
    expect(screen.queryByText(/Can't undo/)).toBeNull();

    backend.planning.commitNextElsewhere(EMAIL);
    await setupChangedElsewhere();

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Undo the Rent payment' })).toBeNull(),
    );
    expect(screen.queryByRole('button', { name: 'Undo the Car loan payment' })).toBeNull();
    expect(screen.getByText('✓ Paid $800.00 on Nov 20, 2026')).toBeTruthy();
    expect(screen.getByText('✓ Paid $150.00 on Nov 20, 2026')).toBeTruthy();
    // A bill has no balance to correct; a debt is pointed to Setup.
    expect(screen.getByText("Can't undo after a newer plan.")).toBeTruthy();
    expect(
      screen.getByText("Can't undo after a newer plan. To correct the balance, edit it in Setup."),
    ).toBeTruthy();
  });
});
