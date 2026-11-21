/**
 * Query keys for the payday flow: the dashboard, plans and payments.
 *
 * Every planning query starts with `planningKeys.all`. The backend marks a draft plan out of
 * date whenever income, bills, essentials, debts, goals, the balance or settings change, so
 * every setup change invalidates this one prefix (ADR 0014).
 */
export const planningKeys = {
  all: ['planning'] as const,
  dashboard: () => [...planningKeys.all, 'dashboard'] as const,
  paychecks: () => [...planningKeys.all, 'paychecks'] as const,
  plans: () => [...planningKeys.all, 'plans'] as const,
  plan: (id: string) => [...planningKeys.plans(), id] as const,
  billPayments: (billId: string) => [...planningKeys.all, 'payments', 'bill', billId] as const,
  debtPayments: (debtId: string) => [...planningKeys.all, 'payments', 'debt', debtId] as const,
};
