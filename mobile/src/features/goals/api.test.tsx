import { act, waitFor } from '@testing-library/react-native';

import type { FakeBackend } from '@/test/fakeBackend';
import { EMAIL, renderWithClient, signedInBackend } from '@/test/hooks';

import { type GoalRequest, useCreateGoal, useDeleteGoal, useGoals, useUpdateGoal } from './api';

jest.mock('@/api/config', () => ({ API_BASE_URL: 'http://api.test' }));
jest.mock('expo-secure-store', () => jest.requireActual('@/test/fakeSecureStore'));

const CAMERA: GoalRequest = {
  name: 'Camera',
  kind: 'purchase',
  target_cents: 89999,
  current_cents: 0,
  priority: 2,
  deadline: '2027-03-01',
};

let backend: FakeBackend;

beforeEach(async () => {
  backend = await signedInBackend();
});

function useGoalHooks() {
  return {
    list: useGoals(),
    create: useCreateGoal(),
    update: useUpdateGoal(),
    remove: useDeleteGoal(),
  };
}

it('creates a goal and shows it in the list', async () => {
  const { result } = await renderWithClient(useGoalHooks);
  await waitFor(() => expect(result.current.list.data).toEqual([]));

  await act(() => result.current.create.mutateAsync(CAMERA));

  expect(result.current.list.data?.map((g) => g.name)).toEqual(['Camera']);
});

it('sends a cleared deadline as an explicit null on PUT', async () => {
  const goal = backend.seed(EMAIL, '/goals', CAMERA);
  const { result } = await renderWithClient(useGoalHooks);
  await waitFor(() => expect(result.current.list.isSuccess).toBe(true));

  await act(() =>
    result.current.update.mutateAsync({ id: goal.id, body: { ...CAMERA, deadline: null } }),
  );

  const sent = backend.lastBody(`PUT /goals/${goal.id}`) as Record<string, unknown>;
  expect(sent).toHaveProperty('deadline', null);
  expect(result.current.list.data?.[0]?.deadline).toBeNull();
});

it('reports a second emergency goal as the backend words it', async () => {
  backend.seed(EMAIL, '/goals', { ...CAMERA, name: 'Emergency fund', kind: 'emergency' });
  const { result } = await renderWithClient(useGoalHooks);
  await waitFor(() => expect(result.current.list.isSuccess).toBe(true));

  const error = await act(() =>
    result.current.create.mutateAsync({ ...CAMERA, kind: 'emergency' }).catch((e: unknown) => e),
  );

  expect(error).toMatchObject({
    status: 409,
    code: 'emergency_goal_exists',
    message: 'You already have an emergency fund goal. Change that one instead.',
  });
});

it('deletes a goal', async () => {
  const goal = backend.seed(EMAIL, '/goals', CAMERA);
  const { result } = await renderWithClient(useGoalHooks);
  await waitFor(() => expect(result.current.list.data).toHaveLength(1));

  await act(() => result.current.remove.mutateAsync(goal.id));

  expect(result.current.list.data).toEqual([]);
});
