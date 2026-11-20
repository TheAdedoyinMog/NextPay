import { onboardingSteps } from './OnboardingScreen';

jest.mock('@/api/config', () => ({ API_BASE_URL: 'http://api.test' }));

const loaded = <T>(data: T[]) => ({ isSuccess: true, data });
const failed = { isSuccess: false, data: undefined };

describe('onboardingSteps', () => {
  it('asks for everything on a new account', () => {
    expect(onboardingSteps(loaded([]), loaded([]))).toEqual(['income', 'balance', 'goal']);
  });

  it('leaves out a step that is already done', () => {
    expect(onboardingSteps(loaded([{}]), loaded([]))).toEqual(['income', 'goal']);
    expect(onboardingSteps(loaded([]), loaded([{ kind: 'emergency' }]))).toEqual([
      'income',
      'balance',
    ]);
    expect(onboardingSteps(loaded([{}]), loaded([{ kind: 'emergency' }]))).toEqual(['income']);
  });

  it('still offers the emergency fund when the only goals are other kinds', () => {
    expect(
      onboardingSteps(loaded([{}]), loaded([{ kind: 'savings' }, { kind: 'purchase' }])),
    ).toEqual(['income', 'goal']);
  });

  it('keeps a step whose list failed to load', () => {
    expect(onboardingSteps(failed, failed)).toEqual(['income', 'balance', 'goal']);
  });
});
