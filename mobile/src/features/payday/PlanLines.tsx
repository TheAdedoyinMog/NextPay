/**
 * A plan's lines in waterfall order, grouped by tier, each with the engine's explanation as
 * it is. On a committed plan, bill and debt lines can be marked paid, and a payment can be
 * undone until the next plan is committed (the server says when, as `can_undo`).
 */
import { useRef } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { ActionButton, confirmDelete, FormError, formErrors } from '@/components/form';
import { SectionTitle } from '@/components/screens';
import { colors, spacing } from '@/components/theme';
import { useBills } from '@/features/bills/api';
import { useDebts } from '@/features/debts/api';
import { formatCalendarDate } from '@/lib/dates';
import { formatCents } from '@/lib/formatCents';
import { newId } from '@/lib/ids';

import {
  type BillPayment,
  type DebtPayment,
  type Plan,
  type PlanLine,
  useBillPayments,
  useDebtPayments,
  usePayBill,
  usePayDebt,
  useUndoBillPayment,
  useUndoDebtPayment,
} from './api';

const CAN_UNDO = 'You can undo it until your next plan is committed.';
const TOO_LATE = "Can't undo after a newer plan.";
const TOO_LATE_DEBT = `${TOO_LATE} To correct the balance, edit it in Setup.`;

const TIER_TITLES: Record<PlanLine['tier'], string> = {
  bill: 'Bills',
  essential: 'Essentials',
  debt_minimum: 'Debt payments',
  emergency_fund: 'Emergency fund',
  goal: 'Goals',
};

/** Runs of lines with the same tier, in the plan's own order (it is already the waterfall's). */
export function groupByTier(
  lines: readonly PlanLine[],
): { tier: PlanLine['tier']; lines: PlanLine[] }[] {
  const groups: { tier: PlanLine['tier']; lines: PlanLine[] }[] = [];
  for (const line of [...lines].sort((a, b) => a.position - b.position)) {
    const last = groups.at(-1);
    if (last && last.tier === line.tier) {
      last.lines.push(line);
    } else {
      groups.push({ tier: line.tier, lines: [line] });
    }
  }
  return groups;
}

export function PlanLines({ plan }: { plan: Plan }) {
  const canPay = plan.status === 'committed';
  return (
    <>
      {groupByTier(plan.allocations).map((group) => (
        <View key={`${group.tier}-${group.lines[0]?.position}`}>
          <SectionTitle>{TIER_TITLES[group.tier]}</SectionTitle>
          {group.lines.map((line) => (
            <LineRow key={line.position} line={line} plan={plan} canPay={canPay} />
          ))}
        </View>
      ))}
    </>
  );
}

function LineRow({ line, plan, canPay }: { line: PlanLine; plan: Plan; canPay: boolean }) {
  return (
    <View
      style={styles.line}
      accessibilityLabel={`${line.name}: ${formatCents(line.funded_cents)}`}
    >
      <View style={styles.lineHeader}>
        <Text style={styles.name}>{line.name}</Text>
        <Text style={styles.amount}>{formatCents(line.funded_cents)}</Text>
      </View>
      <Text style={styles.explanation}>{line.explanation}</Text>
      {line.shortfall_cents > 0 ? (
        <Text style={styles.short}>Short by {formatCents(line.shortfall_cents)}</Text>
      ) : null}
      {canPay && line.target_id && line.tier === 'bill' ? (
        <BillPay billId={line.target_id} dueDate={line.due_date} />
      ) : null}
      {canPay && line.target_id && line.tier === 'debt_minimum' ? (
        <DebtPay debtId={line.target_id} since={plan.paycheck.pay_date} />
      ) : null}
    </View>
  );
}

/**
 * One id per "Mark paid", kept until the server has it. A second tap, or a retry after a
 * timeout whose request did arrive, sends the same id, and the server records one payment.
 */
function usePaymentId() {
  const id = useRef<string | null>(null);
  return {
    current: () => (id.current ??= newId()),
    done: () => {
      id.current = null;
    },
  };
}

function BillPay({ billId, dueDate }: { billId: string; dueDate: string | null }) {
  const bills = useBills();
  const payments = useBillPayments(billId);
  const pay = usePayBill();
  const undo = useUndoBillPayment();
  const paymentId = usePaymentId();
  const bill = bills.data?.find((candidate) => candidate.id === billId);
  if (!bill || !payments.isSuccess) {
    return null;
  }
  const paid = payments.data.find((payment) => payment.due_date === dueDate);
  const send = () =>
    pay.mutate({ billId, paymentId: paymentId.current(), dueDate }, { onSuccess: paymentId.done });
  const ask = () =>
    confirmDelete({
      title: `Mark ${bill.name} paid?`,
      message: `Records ${formatCents(bill.amount_cents)} paid today${
        dueDate ? ` for the ${formatCalendarDate(dueDate)} bill` : ''
      }. ${CAN_UNDO}`,
      confirmLabel: 'Mark paid',
      onConfirm: send,
    });
  const sendUndo = (payment: Payment) =>
    undo.mutate({ billId, paymentId: payment.id }, { onSuccess: () => undo.reset() });
  return (
    <PayStatus
      label={bill.name}
      reservedCents={bill.reserved_cents}
      paid={paid ?? null}
      isPending={pay.isPending}
      error={pay.error}
      onPay={pay.isError ? send : ask}
      tooLate={TOO_LATE}
      undo={{
        isPending: undo.isPending,
        error: undo.error,
        onUndo: (payment) =>
          undo.isError
            ? sendUndo(payment)
            : askUndo(bill.name, payment, 'what it took from the money set aside', () =>
                sendUndo(payment),
              ),
      }}
    />
  );
}

function DebtPay({ debtId, since }: { debtId: string; since: string }) {
  const debts = useDebts();
  const payments = useDebtPayments(debtId);
  const pay = usePayDebt();
  const undo = useUndoDebtPayment();
  const paymentId = usePaymentId();
  const debt = debts.data?.find((candidate) => candidate.id === debtId);
  if (!debt || !payments.isSuccess) {
    return null;
  }
  // Calendar dates as YYYY-MM-DD strings compare correctly as text.
  const paid = payments.data.find((payment) => payment.paid_on >= since);
  const send = () =>
    pay.mutate({ debtId, paymentId: paymentId.current() }, { onSuccess: paymentId.done });
  const ask = () =>
    confirmDelete({
      title: `Mark ${debt.name} paid?`,
      message: `Records your minimum payment of ${formatCents(
        debt.minimum_payment_cents,
      )} paid today, or what's left if that is less. ${CAN_UNDO}`,
      confirmLabel: 'Mark paid',
      onConfirm: send,
    });
  const sendUndo = (payment: Payment) =>
    undo.mutate({ debtId, paymentId: payment.id }, { onSuccess: () => undo.reset() });
  return (
    <PayStatus
      label={debt.name}
      reservedCents={debt.reserved_cents}
      paid={paid ?? null}
      isPending={pay.isPending}
      error={pay.error}
      onPay={pay.isError ? send : ask}
      tooLate={TOO_LATE_DEBT}
      undo={{
        isPending: undo.isPending,
        error: undo.error,
        onUndo: (payment) =>
          undo.isError
            ? sendUndo(payment)
            : askUndo(
                debt.name,
                payment,
                'what it took from the money set aside and from what you owe',
                () => sendUndo(payment),
              ),
      }}
    />
  );
}

type Payment = BillPayment | DebtPayment;

/** Asks before undoing. `putsBack` says in words what the server puts back, never a sum. */
function askUndo(label: string, payment: Payment, putsBack: string, onConfirm: () => void) {
  confirmDelete({
    title: `Undo the ${label} payment?`,
    message: `Removes the ${formatCents(payment.amount_cents)} payment from ${formatCalendarDate(
      payment.paid_on,
    )} and puts back ${putsBack}. Safe to Spend on Home updates. You can mark it paid again.`,
    confirmLabel: 'Undo payment',
    onConfirm,
  });
}

function PayStatus(props: {
  label: string;
  reservedCents: number;
  paid: Payment | null;
  isPending: boolean;
  error: unknown;
  /** After a failure, pressing again retries at once with the same payment id. */
  onPay: () => void;
  /** Shown instead of Undo once a newer plan is committed (the server's `can_undo`). */
  tooLate: string;
  /** After a failure, pressing again retries at once: undoing twice undoes once. */
  undo: { isPending: boolean; error: unknown; onUndo: (payment: Payment) => void };
}) {
  const { paid, undo } = props;
  return (
    <View style={styles.pay}>
      <Text style={styles.muted}>Set aside now: {formatCents(props.reservedCents)}</Text>
      {paid ? (
        <>
          <Text style={styles.paid}>
            ✓ Paid {formatCents(paid.amount_cents)} on {formatCalendarDate(paid.paid_on)}
          </Text>
          {paid.can_undo ? (
            <>
              <FormError message={formErrors(undo.error, {}).form} />
              <ActionButton
                title={undo.error ? 'Try undoing again' : 'Undo'}
                accessibilityLabel={
                  undo.error
                    ? `Try undoing the ${props.label} payment again`
                    : `Undo the ${props.label} payment`
                }
                variant="secondary"
                isPending={undo.isPending}
                onPress={() => undo.onUndo(paid)}
              />
            </>
          ) : (
            <Text style={styles.muted}>{props.tooLate}</Text>
          )}
        </>
      ) : (
        <>
          <FormError message={formErrors(props.error, {}).form} />
          <ActionButton
            title={props.error ? 'Try again' : 'Mark paid'}
            accessibilityLabel={
              props.error ? `Try paying ${props.label} again` : `Mark ${props.label} paid`
            }
            variant="secondary"
            isPending={props.isPending}
            onPress={props.onPay}
          />
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  line: {
    borderBottomColor: colors.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
    gap: spacing.xs,
    paddingVertical: spacing.m,
  },
  lineHeader: { flexDirection: 'row', justifyContent: 'space-between' },
  name: { color: colors.text, flex: 1, fontSize: 17, fontWeight: '600' },
  amount: { color: colors.text, fontSize: 17, fontVariant: ['tabular-nums'], fontWeight: '600' },
  explanation: { color: colors.label, fontSize: 15, lineHeight: 21 },
  short: { color: colors.error, fontSize: 15, fontWeight: '600' },
  pay: { gap: spacing.xs },
  muted: { color: colors.muted, fontSize: 14 },
  paid: { color: colors.text, fontSize: 15 },
});
