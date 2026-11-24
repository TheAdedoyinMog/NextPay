/**
 * The fake backend's payday routes: dashboard, paychecks, plans and payments. It can't run the
 * engine, so a test gives it the plan to return (`planning.template`). It copies the rules
 * the app depends on (ADR 0011, ADR 0015):
 *
 * - Inputs have a version that setup changes, a different actual amount, or a different
 *   balance raise. A draft made at an older version is out of date.
 * - Planning a paycheck at the same version returns the same draft (200); otherwise a new
 *   version replaces it. A paycheck with a committed plan can't be planned again (409).
 * - Committing a committed plan returns it unchanged. An out-of-date or superseded draft is
 *   refused (409). Committing adds each bill, debt and goal line to that target's
 *   `reserved_cents` (and a goal's `current_cents`).
 * - A payment with a known id returns the first one (200) and changes nothing. A new one
 *   draws the target's reserve down, never below 0, and lowers a debt's balance.
 * - The dashboard's Safe to Spend is the newest committed plan's, less what payments made
 *   after that commit paid beyond their reserves; past $0 it is a shortfall (ADR 0016).
 * - Undoing a payment puts back what it drew from the reserve and took off the balance, and
 *   drops it from lists and from Safe to Spend. Undoing it again returns it unchanged. After
 *   a later commit it is refused (409) and `can_undo` is false (ADR 0017). Unlike the real
 *   hash, an undo here makes every draft out of date; the backend's tests cover the rest.
 */
import type { components } from '@/api/schema';

type Plan = components['schemas']['PlanResponse'];
type Line = components['schemas']['AllocationResponse'];
type Paycheck = components['schemas']['PaycheckResponse'];
type Item = Record<string, unknown> & { id: string };

export const TODAY = '2026-11-20';
const NOW = '2026-11-20T15:00:00Z';

export type PaydaySeed = {
  income_source_id: string;
  income_source_name: string;
  pay_date: string;
  expected_amount_cents: number;
};

/** What a test wants the next plan to say. Lines need only what the test cares about. */
export type PlanTemplate = {
  safe_to_spend_cents: number;
  reserve_deficit_cents?: number;
  summary?: string;
  allocations: (Partial<Line> & Pick<Line, 'tier' | 'name' | 'funded_cents'>)[];
  goal_projections?: Plan['goal_projections'];
};

type StoredPlan = Plan & { email: string; inputsVersion: number; order?: number };

interface Deps {
  json: (status: number, body: unknown) => Response;
  error: (status: number, code: string, message: string) => Response;
  items: (email: string, path: string) => Item[];
}

export function createFakePlanning({ json, error, items }: Deps) {
  const versions = new Map<string, number>();
  const paydays = new Map<string, { current: PaydaySeed | null; next: PaydaySeed | null }>();
  const actuals = new Map<string, number | null>();
  const plans: StoredPlan[] = [];
  let serial = 0;

  const version = (email: string) => versions.get(email) ?? 0;
  const paycheckKey = (email: string, sourceId: string, payDate: string) =>
    `${email}|${sourceId}|${payDate}`;

  function seedFor(email: string, sourceId: string, payDate: string): PaydaySeed | null {
    const days = paydays.get(email);
    return (
      [days?.current, days?.next].find(
        (seed) => seed?.income_source_id === sourceId && seed.pay_date === payDate,
      ) ?? null
    );
  }

  function currentPlan(email: string, seed: PaydaySeed): StoredPlan | null {
    const own = plans.filter(
      (plan) =>
        plan.email === email &&
        plan.paycheck.income_source_id === seed.income_source_id &&
        plan.paycheck.pay_date === seed.pay_date &&
        plan.status !== 'superseded',
    );
    return own.at(-1) ?? null;
  }

  const isOutOfDate = (plan: StoredPlan) =>
    plan.status === 'draft' && plan.inputsVersion !== version(plan.email);

  function paycheck(email: string, seed: PaydaySeed): Paycheck {
    const actual = actuals.get(paycheckKey(email, seed.income_source_id, seed.pay_date)) ?? null;
    const plan = currentPlan(email, seed);
    return {
      id: `paycheck-${seed.pay_date}`,
      income_source_id: seed.income_source_id,
      income_source_name: seed.income_source_name,
      income_source_archived: false,
      pay_date: seed.pay_date,
      expected_amount_cents: seed.expected_amount_cents,
      actual_amount_cents: actual,
      amount_cents: actual ?? seed.expected_amount_cents,
      plan: plan && {
        id: plan.id,
        version: plan.version,
        status: plan.status,
        safe_to_spend_cents: plan.safe_to_spend_cents,
        is_out_of_date: isOutOfDate(plan),
      },
    };
  }

  /** The plan as the API returns it, with today's out-of-date flag. */
  function view(plan: StoredPlan): Plan {
    const { email, inputsVersion: _version, order: _order, ...body } = plan;
    const seed = seedFor(email, plan.paycheck.income_source_id, plan.paycheck.pay_date);
    return {
      ...body,
      is_out_of_date: isOutOfDate(plan),
      paycheck: seed ? paycheck(email, seed) : plan.paycheck,
    };
  }

  const planning = {
    template: null as PlanTemplate | null,

    setPaydays(email: string, days: { current?: PaydaySeed; next?: PaydaySeed }): void {
      paydays.set(email, { current: days.current ?? null, next: days.next ?? null });
    },

    /** Something the engine reads changed: drafts made before now are out of date. */
    bump(email: string): void {
      versions.set(email, version(email) + 1);
    },

    plans(): Plan[] {
      return plans.map(view);
    },

    /** The next paycheck's plan, made and committed on another device. */
    commitNextElsewhere(email: string): void {
      const next = paydays.get(email)?.next;
      if (!next) throw new Error('fakePlanning: set a next payday first');
      generate(email, next.income_source_id, next.pay_date);
      const draft = currentPlan(email, next);
      if (draft) commit(draft);
    },

    handle(
      method: string,
      path: string,
      body: Record<string, unknown>,
      email: string,
    ): Response | null {
      const parts = path.split('/').filter(Boolean);
      if (method === 'GET' && path === '/dashboard') {
        return json(200, dashboard(email));
      }
      if (method === 'PUT' && parts[0] === 'income-sources' && parts[2] === 'paychecks') {
        return recordActual(email, parts[1] ?? '', parts[3] ?? '', body);
      }
      if (method === 'POST' && path === '/plans') {
        return generate(email, String(body.income_source_id), String(body.pay_date));
      }
      if (parts[0] === 'plans' && parts[1]) {
        const plan = plans.find(
          (candidate) => candidate.id === parts[1] && candidate.email === email,
        );
        if (!plan) return error(404, 'not_found', 'Not found.');
        if (method === 'GET' && parts.length === 2) return json(200, view(plan));
        if (method === 'POST' && parts[2] === 'commit') return commit(plan);
      }
      if ((parts[0] === 'bills' || parts[0] === 'debts') && parts[2] === 'payments') {
        if (method === 'POST' && parts[4] === 'undo') {
          return undo(email, parts[1] ?? '', parts[3] ?? '');
        }
        return payment(method, email, parts[0], parts[1] ?? '', body);
      }
      return null;
    },
  };

  function dashboard(email: string) {
    const days = paydays.get(email);
    const committed = plans.filter(
      (plan) =>
        plan.email === email && plan.status === 'committed' && plan.paycheck.pay_date <= TODAY,
    );
    const newest = committed.at(-1);
    const snapshots = items(email, '/balance-snapshots');
    // Every fake time is NOW, so "after the commit" is told by the order things happened.
    const beyond = [...payments.values()]
      .filter(
        (p) =>
          p.email === email && !p.undone_at && newest && (p.order as number) > (newest.order ?? 0),
      )
      .reduce((sum, p) => sum + (p.beyond as number), 0);
    const free = newest ? newest.safe_to_spend_cents - newest.reserve_deficit_cents - beyond : 0;
    return {
      today: TODAY,
      current_paycheck: days?.current ? paycheck(email, days.current) : null,
      next_paycheck: days?.next ? paycheck(email, days.next) : null,
      safe_to_spend: newest
        ? {
            plan_id: newest.id,
            pay_date: newest.paycheck.pay_date,
            income_source_name: newest.paycheck.income_source_name,
            safe_to_spend_cents: Math.max(free, 0),
            reserve_deficit_cents: Math.max(-free, 0),
            paid_beyond_reserves_cents: beyond,
          }
        : null,
      balance: snapshots[0] ?? null,
    };
  }

  function recordActual(
    email: string,
    sourceId: string,
    payDate: string,
    body: Record<string, unknown>,
  ) {
    const seed = seedFor(email, sourceId, payDate);
    if (!seed) return error(422, 'invalid_input', `${payDate} is not a payday.`);
    const key = paycheckKey(email, sourceId, payDate);
    const cents = body.actual_amount_cents as number | null;
    if (typeof cents === 'number' && cents < 0) {
      return json(422, {
        error: {
          code: 'validation_error',
          message: 'Check these fields: actual_amount_cents',
          fields: { actual_amount_cents: 'Input should be greater than or equal to 0' },
        },
      });
    }
    if ((actuals.get(key) ?? null) !== cents) {
      actuals.set(key, cents);
      planning.bump(email);
    }
    return json(200, paycheck(email, seed));
  }

  function generate(email: string, sourceId: string, payDate: string): Response {
    const seed = seedFor(email, sourceId, payDate);
    if (!seed) return error(422, 'invalid_input', `${payDate} is not a payday.`);
    const existing = currentPlan(email, seed);
    if (existing?.status === 'committed') {
      return error(
        409,
        'paycheck_already_committed',
        'This paycheck already has a committed plan.',
      );
    }
    if (existing && !isOutOfDate(existing)) {
      return json(200, view(existing));
    }
    if (existing) existing.status = 'superseded';
    const template = planning.template;
    if (!template) throw new Error('fakePlanning: set planning.template before planning');
    serial += 1;
    const balance = items(email, '/balance-snapshots')[0];
    const pay = paycheck(email, seed);
    const plan: StoredPlan = {
      email,
      inputsVersion: version(email),
      id: `plan-${serial}`,
      version: (existing?.version ?? 0) + 1,
      status: 'draft',
      is_out_of_date: false,
      committed_at: null,
      engine_version: '1.2.3',
      as_of: TODAY,
      paycheck: pay,
      next_pay_date: paydays.get(email)?.next?.pay_date ?? payDate,
      paycheck_amount_cents: pay.amount_cents,
      available_balance_cents: (balance?.amount_cents as number | undefined) ?? 0,
      balance_as_of: (balance?.as_of as string | undefined) ?? null,
      safe_to_spend_cents: template.safe_to_spend_cents,
      reserve_deficit_cents: template.reserve_deficit_cents ?? 0,
      summary: template.summary ?? `Safe to Spend is ${template.safe_to_spend_cents} cents.`,
      allocations: template.allocations.map((line, position) => ({
        position,
        target_id: null,
        requested_cents: line.funded_cents,
        shortfall_cents: 0,
        reason: 'bill_due',
        total_cents: line.funded_cents,
        set_aside_cents: 0,
        due_date: null,
        paychecks: null,
        days_covered: null,
        days_in_period: null,
        share_bps: null,
        paid_cents: 0,
        paid_on: null,
        paid_ahead: 0,
        paid_through: null,
        paid_ahead_on: null,
        explanation: `${line.name}: explained by the engine.`,
        ...line,
      })),
      goal_projections: template.goal_projections ?? [],
      created_at: NOW,
    };
    plans.push(plan);
    return json(201, view(plan));
  }

  function commit(plan: StoredPlan): Response {
    if (plan.status === 'committed') return json(200, view(plan));
    if (plan.status === 'superseded') {
      return error(
        409,
        'plan_superseded',
        'A newer plan replaced this one. Commit the newer plan.',
      );
    }
    if (isOutOfDate(plan)) {
      return error(
        409,
        'plan_out_of_date',
        'Your details have changed since this plan was made. Generate a new plan.',
      );
    }
    for (const line of plan.allocations) {
      const path = {
        bill: '/bills',
        debt_minimum: '/debts',
        emergency_fund: '/goals',
        goal: '/goals',
      }[line.tier as string];
      const target = path && items(plan.email, path).find((item) => item.id === line.target_id);
      if (target) {
        target.reserved_cents = (target.reserved_cents as number) + line.funded_cents;
        if (path === '/goals')
          target.current_cents = (target.current_cents as number) + line.funded_cents;
      }
    }
    plan.status = 'committed';
    plan.committed_at = NOW;
    plan.order = ++order;
    // A commit changes reserves, which every other draft read.
    versions.set(plan.email, version(plan.email) + 1);
    plan.inputsVersion = version(plan.email);
    return json(200, view(plan));
  }

  const payments = new Map<string, Item>();
  /** Counts commits and payments, so the dashboard knows which payments came after a commit. */
  let order = 0;

  /** The order of the user's newest commit, for any paycheck; 0 if none. */
  const latestCommit = (email: string) =>
    Math.max(0, ...plans.filter((plan) => plan.email === email).map((plan) => plan.order ?? 0));

  /** A payment as the API returns it. */
  function shape(record: Item) {
    const {
      email,
      target_id: _t,
      beyond: _b,
      order: recorded,
      drawn: _d,
      reduced: _r,
      ...rest
    } = record;
    return {
      ...rest,
      can_undo: !record.undone_at && (recorded as number) > latestCommit(email as string),
    };
  }

  function undo(email: string, targetId: string, paymentId: string): Response {
    const record = payments.get(paymentId);
    if (!record || record.email !== email || record.target_id !== targetId) {
      return error(404, 'not_found', 'Not found.');
    }
    if (record.undone_at) return json(200, shape(record));
    if (!shape(record).can_undo) {
      return error(
        409,
        'payment_undo_too_late',
        "A newer plan was committed after this payment, so it can't be undone. If the payment didn't happen, correct the balance instead.",
      );
    }
    const kind = 'bill_id' in record ? '/bills' : '/debts';
    const target = items(email, kind).find((item) => item.id === targetId);
    if (target) {
      target.reserved_cents = (target.reserved_cents as number) + (record.drawn as number);
      if (kind === '/debts') {
        target.balance_cents = (target.balance_cents as number) + (record.reduced as number);
      }
    }
    record.undone_at = NOW;
    planning.bump(email);
    return json(200, shape(record));
  }

  function payment(
    method: string,
    email: string,
    kind: string,
    targetId: string,
    body: Record<string, unknown>,
  ) {
    const target = items(email, `/${kind}`).find((item) => item.id === targetId);
    if (!target) return error(404, 'not_found', 'Not found.');
    const own = [...payments.values()].filter(
      (p) => p.target_id === targetId && p.email === email && !p.undone_at,
    );
    if (method === 'GET') {
      return json(200, { items: own.reverse().map(shape) });
    }
    const id = typeof body.id === 'string' ? body.id : `payment-${payments.size + 1}`;
    const earlier = payments.get(id);
    if (earlier) {
      if (earlier.email !== email || earlier.target_id !== targetId) {
        return error(
          409,
          'payment_id_conflict',
          'This payment id is already used by another payment. Make a new one.',
        );
      }
      return json(200, shape(earlier));
    }
    const amount =
      kind === 'bills'
        ? (target.amount_cents as number)
        : Math.min(target.minimum_payment_cents as number, target.balance_cents as number);
    const record: Item = {
      id,
      email,
      target_id: targetId,
      [kind === 'bills' ? 'bill_id' : 'debt_id']: targetId,
      due_date: (body.due_date as string | null) ?? TODAY,
      paid_on: TODAY,
      amount_cents: amount,
      created_at: NOW,
      undone_at: null,
      beyond: Math.max(amount - (target.reserved_cents as number), 0),
      drawn: Math.min(amount, target.reserved_cents as number),
      reduced: kind === 'debts' ? Math.min(amount, target.balance_cents as number) : 0,
      order: ++order,
    };
    payments.set(id, record);
    target.reserved_cents = Math.max((target.reserved_cents as number) - amount, 0);
    if (kind === 'debts')
      target.balance_cents = Math.max((target.balance_cents as number) - amount, 0);
    planning.bump(email);
    return json(201, shape(record));
  }

  return planning;
}

export type FakePlanning = ReturnType<typeof createFakePlanning>;
