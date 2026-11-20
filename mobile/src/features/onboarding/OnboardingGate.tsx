/**
 * Whether the signed-in app opens on onboarding. Decided from the server, not a flag on the
 * phone: an account with no income sources needs setting up, on any device. (A flag would
 * also need AsyncStorage, a native module, and so a new build.)
 *
 * The decision is made once per sign-in and then held, for two reasons:
 * - Onboarding's first step adds an income source, which refetches the list. Without holding
 *   the decision, the app would leave onboarding in the middle.
 * - Deleting the last income source later must not throw the user back into onboarding.
 *
 * It is held above the navigator, at the root, because Expo Router can recreate the signed-in
 * layout when its protected routes change, which would lose state kept there. It goes back to
 * "deciding" whenever nobody is signed in, so the next account is decided afresh.
 */
import { createContext, type ReactNode, useContext, useEffect, useState } from 'react';

import { useSession } from '@/features/auth/SessionProvider';
import { useIncomeSources } from '@/features/income/api';

export type OnboardingDecision = 'deciding' | 'onboarding' | 'done';

type Held = { decision: OnboardingDecision; setDecision: (decision: OnboardingDecision) => void };

const HeldDecision = createContext<Held | null>(null);

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const { status } = useSession();
  const [decision, setDecision] = useState<OnboardingDecision>('deciding');
  if (status !== 'signedIn' && decision !== 'deciding') {
    setDecision('deciding'); // signed out: decide again for whoever signs in next
  }
  return (
    <HeldDecision.Provider value={{ decision, setDecision }}>{children}</HeldDecision.Provider>
  );
}

function useHeld(): Held {
  const held = useContext(HeldDecision);
  if (!held) {
    throw new Error('useOnboardingDecision needs an OnboardingProvider above it.');
  }
  return held;
}

/** For the signed-in layout: makes the decision from the first income list, then holds it. */
export function useOnboardingDecision() {
  const { decision, setDecision } = useHeld();
  const incomes = useIncomeSources();

  let firstAnswer: OnboardingDecision | null = null;
  if (incomes.isSuccess) {
    firstAnswer = incomes.data.length === 0 ? 'onboarding' : 'done';
  } else if (incomes.isError) {
    firstAnswer = 'done'; // unknown, perhaps offline: open the app, whose screens can retry
  }
  // The decision lives in the provider, so it's set after render, not during it.
  useEffect(() => {
    if (decision === 'deciding' && firstAnswer) {
      setDecision(firstAnswer);
    }
  }, [decision, firstAnswer, setDecision]);

  return decision;
}

/** Called by onboarding's last step (saved or skipped) to open the app. */
export function useFinishOnboarding(): () => void {
  const { setDecision } = useHeld();
  return () => setDecision('done');
}
