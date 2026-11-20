import { ordinal } from '@/lib/dates';
import { formatCents } from '@/lib/formatCents';
import { hundredthsToText } from '@/lib/money';

import type { Debt } from './api';

/** Basis points as a percent, by moving the point: 2499 is "24.99%". */
export function formatApr(bps: number): string {
  return `${hundredthsToText(bps)}%`;
}

/** "24.99% APR · $35.00 minimum · due the 15th". */
export function describeDebt(
  debt: Pick<Debt, 'apr_bps' | 'minimum_payment_cents' | 'due_day'>,
): string {
  return `${formatApr(debt.apr_bps)} APR · ${formatCents(debt.minimum_payment_cents)} minimum · due the ${ordinal(debt.due_day)}`;
}
