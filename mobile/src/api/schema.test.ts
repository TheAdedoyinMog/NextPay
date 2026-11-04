/**
 * PUT replaces a whole resource, so a nullable field must be sent as null, and leaving it
 * out returns a 422 (ADR 0010). These are checked by `tsc`: the `@ts-expect-error` lines
 * stop compiling if the generated types ever make such a field optional.
 */
import type { components } from './schema';

type BillRepeat = Pick<components['schemas']['BillRequest'], 'repeat_every_months'>;
type GoalDeadline = Pick<components['schemas']['GoalRequest'], 'deadline'>;

it('makes a PUT say null on purpose', () => {
  // @ts-expect-error repeat_every_months is required, even though it may be null.
  const billOmitted: BillRepeat = {};
  const billCleared: BillRepeat = { repeat_every_months: null };
  // @ts-expect-error deadline is required, even though it may be null.
  const goalOmitted: GoalDeadline = {};
  const goalCleared: GoalDeadline = { deadline: null };

  expect([billOmitted, billCleared, goalOmitted, goalCleared]).toHaveLength(4);
});
