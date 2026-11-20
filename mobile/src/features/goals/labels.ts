import { formatCalendarDate } from '@/lib/dates';
import { formatCents } from '@/lib/formatCents';

import type { Goal } from './api';
import { GOAL_KIND_OPTIONS } from './GoalForm';

export function describeKind(kind: Goal['kind']): string {
  return GOAL_KIND_OPTIONS.find((option) => option.value === kind)?.label ?? kind;
}

/** "Emergency fund · $200.00 saved · by Mar 1, 2027". Two stored amounts, no arithmetic. */
export function describeGoal(goal: Pick<Goal, 'kind' | 'current_cents' | 'deadline'>): string {
  const parts = [describeKind(goal.kind), `${formatCents(goal.current_cents)} saved`];
  if (goal.deadline) {
    parts.push(`by ${formatCalendarDate(goal.deadline)}`);
  }
  return parts.join(' · ');
}
