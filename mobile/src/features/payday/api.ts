/**
 * The payday loop: the dashboard, recording what a paycheck paid, planning it, committing
 * the plan, and paying bills and debts (ADR 0011, ADR 0015).
 *
 * Every money action is safe to repeat. Recording an amount is a PUT. Planning the same
 * paycheck from the same inputs returns the same draft. Committing a committed plan returns
 * it unchanged. A payment carries an id the app made, so a retry returns the first payment.
 * Undoing an undone payment returns it unchanged (ADR 0017).
 */
import { type QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';
import { billKeys } from '@/features/bills/api';
import { debtKeys } from '@/features/debts/api';
import { goalKeys } from '@/features/goals/api';
import { planningKeys } from '@/features/planning/keys';

export type Dashboard = components['schemas']['DashboardResponse'];
export type Paycheck = components['schemas']['PaycheckResponse'];
export type Plan = components['schemas']['PlanResponse'];
export type PlanLine = components['schemas']['AllocationResponse'];
export type BillPayment = components['schemas']['BillPaymentResponse'];
export type DebtPayment = components['schemas']['DebtPaymentResponse'];

/** A paycheck is named by its income source and pay date (ADR 0011). */
export type PaycheckKey = { incomeSourceId: string; payDate: string };

export function useDashboard() {
  return useQuery({
    queryKey: planningKeys.dashboard(),
    queryFn: () => unwrap(api.GET('/dashboard')),
  });
}

export function usePlan(id: string | undefined) {
  return useQuery({
    queryKey: planningKeys.plan(id ?? ''),
    queryFn: () => unwrap(api.GET('/plans/{plan_id}', { params: { path: { plan_id: id ?? '' } } })),
    enabled: Boolean(id),
  });
}

/** After a commit or payment: plans and the dashboard, and the reserves on bills, debts, goals. */
function afterMoneyMoved(queryClient: QueryClient): Promise<unknown> {
  return Promise.all(
    [planningKeys.all, billKeys.all, debtKeys.all, goalKeys.all].map((queryKey) =>
      queryClient.invalidateQueries({ queryKey }),
    ),
  );
}

/** What the paycheck actually paid. A PUT: sending it twice is the same as once. */
export function useRecordActualAmount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ paycheck, cents }: { paycheck: PaycheckKey; cents: number }) =>
      unwrap(
        api.PUT('/income-sources/{income_source_id}/paychecks/{pay_date}', {
          params: {
            path: { income_source_id: paycheck.incomeSourceId, pay_date: paycheck.payDate },
          },
          body: { actual_amount_cents: cents },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: planningKeys.all }),
  });
}

/**
 * Plans a paycheck. Unchanged inputs return the same draft, so a retry is harmless. The new
 * plan is put in the cache, so the plan screen opens without another request.
 */
export function useGeneratePlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (paycheck: PaycheckKey) =>
      unwrap(
        api.POST('/plans', {
          body: { income_source_id: paycheck.incomeSourceId, pay_date: paycheck.payDate },
        }),
      ),
    onSuccess: async (plan) => {
      await queryClient.invalidateQueries({ queryKey: planningKeys.all });
      queryClient.setQueryData(planningKeys.plan(plan.id), plan);
    },
  });
}

/** Commits a draft. Committing it again returns it unchanged, so a retry is harmless. */
export function useCommitPlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) =>
      unwrap(api.POST('/plans/{plan_id}/commit', { params: { path: { plan_id: planId } } })),
    onSuccess: async (plan) => {
      queryClient.setQueryData(planningKeys.plan(plan.id), plan);
      await afterMoneyMoved(queryClient);
    },
  });
}

export function useBillPayments(billId: string | null) {
  return useQuery({
    queryKey: planningKeys.billPayments(billId ?? ''),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/bills/{bill_id}/payments', { params: { path: { bill_id: billId ?? '' } } }),
        )
      ).items,
    enabled: Boolean(billId),
  });
}

export function useDebtPayments(debtId: string | null) {
  return useQuery({
    queryKey: planningKeys.debtPayments(debtId ?? ''),
    queryFn: async () =>
      (
        await unwrap(
          api.GET('/debts/{debt_id}/payments', { params: { path: { debt_id: debtId ?? '' } } }),
        )
      ).items,
    enabled: Boolean(debtId),
  });
}

/**
 * Marks a bill occurrence paid in full. `paymentId` is made once per "Mark paid" and reused
 * on every retry, so the server records one payment however often the request arrives.
 */
export function usePayBill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { billId: string; paymentId: string; dueDate: string | null }) =>
      unwrap(
        api.POST('/bills/{bill_id}/payments', {
          params: { path: { bill_id: args.billId } },
          body: { id: args.paymentId, due_date: args.dueDate },
        }),
      ),
    onSuccess: () => afterMoneyMoved(queryClient),
  });
}

/**
 * Records a debt's minimum payment (or what is left, if less) for the occurrence its plan line
 * names, so a minimum paid early is not reserved again (ADR 0018). Same id rule as bills.
 */
export function usePayDebt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { debtId: string; paymentId: string; dueDate: string | null }) =>
      unwrap(
        api.POST('/debts/{debt_id}/payments', {
          params: { path: { debt_id: args.debtId } },
          body: { id: args.paymentId, due_date: args.dueDate },
        }),
      ),
    onSuccess: () => afterMoneyMoved(queryClient),
  });
}

/**
 * Undoes a bill payment: the server puts back what it drew from the reserve. Undoing it again
 * returns it unchanged, so a double tap or a retry undoes it once.
 */
export function useUndoBillPayment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { billId: string; paymentId: string }) =>
      unwrap(
        api.POST('/bills/{bill_id}/payments/{payment_id}/undo', {
          params: { path: { bill_id: args.billId, payment_id: args.paymentId } },
        }),
      ),
    onSuccess: () => afterMoneyMoved(queryClient),
  });
}

/** Undoes a debt payment: the reserve and the balance go back. Safe to repeat, as for bills. */
export function useUndoDebtPayment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { debtId: string; paymentId: string }) =>
      unwrap(
        api.POST('/debts/{debt_id}/payments/{payment_id}/undo', {
          params: { path: { debt_id: args.debtId, payment_id: args.paymentId } },
        }),
      ),
    onSuccess: () => afterMoneyMoved(queryClient),
  });
}
