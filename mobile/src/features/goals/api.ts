import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';
import { invalidateAfterSetupChange } from '@/features/setup/invalidate';

export type Goal = components['schemas']['GoalResponse'];
export type GoalRequest = components['schemas']['GoalRequest'];
export type GoalKind = GoalRequest['kind'];

export const goalKeys = {
  all: ['goals'] as const,
};

/** Every goal, purchases included (ADR 0004). */
export function useGoals() {
  return useQuery({
    queryKey: goalKeys.all,
    queryFn: async () => (await unwrap(api.GET('/goals'))).items,
  });
}

/** A second emergency goal is refused with 409 `emergency_goal_exists`. */
export function useCreateGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: GoalRequest) => unwrap(api.POST('/goals', { body })),
    onSuccess: () => invalidateAfterSetupChange(queryClient, goalKeys.all),
  });
}

/** PUT replaces the whole goal; `deadline` must be sent, as null for none (ADR 0010). */
export function useUpdateGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: GoalRequest }) =>
      unwrap(api.PUT('/goals/{goal_id}', { params: { path: { goal_id: id } }, body })),
    onSuccess: () => invalidateAfterSetupChange(queryClient, goalKeys.all),
  });
}

/** Deleting releases anything set aside for it: that money is spendable again (ADR 0010). */
export function useDeleteGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE('/goals/{goal_id}', { params: { path: { goal_id: id } } })),
    onSuccess: () => invalidateAfterSetupChange(queryClient, goalKeys.all),
  });
}
