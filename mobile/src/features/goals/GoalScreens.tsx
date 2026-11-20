/** Goals, purchases included (ADR 0004): the list, adding one, and editing or deleting one. */
import { useLocalSearchParams, useRouter } from 'expo-router';

import { ListRow, Screen } from '@/components/screens';
import { EditScaffold, ResourceList } from '@/features/setup/ResourceScreens';
import { formatCents } from '@/lib/formatCents';

import { useCreateGoal, useDeleteGoal, useGoals, useUpdateGoal } from './api';
import { EMPTY_GOAL, GoalForm, goalValues } from './GoalForm';
import { describeGoal } from './labels';

export function GoalListScreen() {
  const router = useRouter();
  return (
    <ResourceList
      query={useGoals()}
      empty={{
        title: 'No goals yet',
        message: 'Save for an emergency fund, a trip, or something you want to buy.',
      }}
      addLabel="Add goal"
      onAdd={() => router.push('/setup/goals/new')}
      renderItem={(goal) => (
        <ListRow
          key={goal.id}
          title={goal.name}
          subtitle={describeGoal(goal)}
          detail={formatCents(goal.target_cents)}
          onPress={() => router.push({ pathname: '/setup/goals/[id]', params: { id: goal.id } })}
        />
      )}
    />
  );
}

export function GoalNewScreen() {
  const router = useRouter();
  const create = useCreateGoal();
  return (
    <Screen>
      <GoalForm
        initial={EMPTY_GOAL}
        submitLabel="Add goal"
        isPending={create.isPending}
        error={create.error}
        onSubmit={(body) => create.mutate(body, { onSuccess: () => router.back() })}
      />
    </Screen>
  );
}

export function GoalEditScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const update = useUpdateGoal();
  return (
    <EditScaffold
      id={id}
      query={useGoals()}
      remove={useDeleteGoal()}
      noun="goal"
      removeLabel="Delete goal"
      confirm={(goal) => ({
        title: `Delete ${goal.name}?`,
        message:
          'Anything set aside for it becomes spendable again. What you entered as saved is forgotten.',
      })}
    >
      {(goal, removeButton) => (
        <GoalForm
          initial={goalValues(goal)}
          submitLabel="Save changes"
          isPending={update.isPending}
          error={update.error}
          onSubmit={(body) =>
            update.mutate({ id: goal.id, body }, { onSuccess: () => router.back() })
          }
        >
          {removeButton}
        </GoalForm>
      )}
    </EditScaffold>
  );
}
