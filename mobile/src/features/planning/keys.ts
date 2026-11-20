/**
 * Query keys for what 3D builds: the paycheck timeline and plans. Defined now so that every
 * setup change already invalidates them.
 *
 * Every planning query must start with `planningKeys.all`, for example
 * `[...planningKeys.all, 'paychecks', { start, end }]` or `[...planningKeys.all, 'plans', id]`.
 * The backend marks a draft plan out of date whenever income, bills, essentials, debts,
 * goals, the balance or settings change, so one prefix invalidation covers them all.
 */
export const planningKeys = {
  all: ['planning'] as const,
  paychecks: () => [...planningKeys.all, 'paychecks'] as const,
  plans: () => [...planningKeys.all, 'plans'] as const,
};
