/** Pay schedules in words. Works on the date strings, never a Date (see lib/dates). */
import type { SelectOption } from '@/components/form';
import { ordinal, parseCalendarDate, weekdayOf } from '@/lib/dates';

import type { Schedule } from './api';

export type Frequency = Schedule['type'];

export const FREQUENCY_OPTIONS: readonly SelectOption<Frequency>[] = [
  { value: 'weekly', label: 'Every week' },
  { value: 'biweekly', label: 'Every two weeks' },
  { value: 'semi_monthly', label: 'Twice a month' },
  { value: 'monthly', label: 'Once a month' },
];

const WEEKDAY_NAMES = [
  'Sunday',
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
];

function weekdayName(date: string): string {
  const parts = parseCalendarDate(date);
  return parts ? (WEEKDAY_NAMES[weekdayOf(parts)] ?? '') : '';
}

/** "Every Friday", "Every other Friday", "The 1st and 15th", "The 15th of each month". */
export function describeSchedule(schedule: Schedule): string {
  switch (schedule.type) {
    case 'weekly':
      return `Every ${weekdayName(schedule.anchor_date)}`;
    case 'biweekly':
      return `Every other ${weekdayName(schedule.anchor_date)}`;
    case 'semi_monthly':
      return `The ${ordinal(schedule.first_day_of_month)} and ${ordinal(schedule.second_day_of_month)}`;
    case 'monthly':
      return `The ${ordinal(schedule.day_of_month)} of each month`;
  }
}
