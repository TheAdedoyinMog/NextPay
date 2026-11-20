import type { SelectOption } from '@/components/form';
import { formatCalendarDate } from '@/lib/dates';

import type { Bill } from './api';

/** The common choices. A bill saved with another interval gets its own option (see below). */
const COMMON_REPEATS: readonly SelectOption<number | null>[] = [
  { value: 1, label: 'Every month' },
  { value: 3, label: 'Every 3 months' },
  { value: 6, label: 'Every 6 months' },
  { value: 12, label: 'Every year' },
  { value: null, label: 'Just once' },
];

export function describeRepeat(months: number | null): string {
  const common = COMMON_REPEATS.find((option) => option.value === months);
  return common?.label ?? `Every ${months} months`;
}

/** The common choices, plus the bill's own interval if it is unusual, so editing keeps it. */
export function repeatOptions(current: number | null): readonly SelectOption<number | null>[] {
  return COMMON_REPEATS.some((option) => option.value === current)
    ? COMMON_REPEATS
    : [...COMMON_REPEATS, { value: current, label: describeRepeat(current) }];
}

/** "Every month from Dec 1, 2026", or "Once, on Dec 1, 2026". */
export function describeBill(bill: Pick<Bill, 'first_due_date' | 'repeat_every_months'>): string {
  const date = formatCalendarDate(bill.first_due_date);
  return bill.repeat_every_months === null
    ? `Once, on ${date}`
    : `${describeRepeat(bill.repeat_every_months)} from ${date}`;
}
