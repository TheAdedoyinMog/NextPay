import { QueryClientProvider } from '@tanstack/react-query';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect, useState } from 'react';

import { createQueryClient } from '@/api/queryClient';
import { SessionProvider, useSession } from '@/features/auth/SessionProvider';
import { OnboardingProvider } from '@/features/onboarding/OnboardingGate';

// Keep the native splash up until we know whether someone is signed in.
void SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const [queryClient] = useState(createQueryClient);
  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <OnboardingProvider>
          <RootNavigator />
        </OnboardingProvider>
      </SessionProvider>
    </QueryClientProvider>
  );
}

/** Signed-in users only reach (app); everyone else only reaches (auth). */
function RootNavigator() {
  const { status } = useSession();
  const isSignedIn = status === 'signedIn';

  useEffect(() => {
    if (status !== 'restoring') {
      void SplashScreen.hideAsync();
    }
  }, [status]);

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Protected guard={isSignedIn} redirectTo="/sign-in">
        <Stack.Screen name="(app)" />
      </Stack.Protected>
      <Stack.Protected guard={!isSignedIn} redirectTo="/">
        <Stack.Screen name="(auth)" />
      </Stack.Protected>
    </Stack>
  );
}
