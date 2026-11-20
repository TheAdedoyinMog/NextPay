import { Stack } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { LoadingState } from '@/components/screens';
import { colors } from '@/components/theme';
import { useOnboardingDecision } from '@/features/onboarding/OnboardingGate';

/**
 * Signed in: onboarding first if the account has no income yet, then the tabs. The navigator
 * stays mounted while deciding, under a loading cover, so the URL the app opened on is kept.
 */
export default function AppLayout() {
  const decision = useOnboardingDecision();
  const isOnboarding = decision === 'onboarding';

  return (
    <>
      <Stack>
        <Stack.Protected guard={isOnboarding} redirectTo="/">
          <Stack.Screen name="onboarding" options={{ title: 'Welcome to NextPay' }} />
        </Stack.Protected>
        <Stack.Protected guard={!isOnboarding} redirectTo="/onboarding">
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        </Stack.Protected>
      </Stack>
      {decision === 'deciding' ? (
        <View testID="deciding-cover" style={styles.cover}>
          <LoadingState />
        </View>
      ) : null}
    </>
  );
}

const styles = StyleSheet.create({
  cover: {
    ...StyleSheet.absoluteFill,
    backgroundColor: colors.background,
    justifyContent: 'center',
  },
});
