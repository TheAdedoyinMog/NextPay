/** The signed-in home. A placeholder until the payday flow arrives. */
import { Button, ScrollView, StyleSheet, Text } from 'react-native';

import { ApiError, errorMessage } from '@/api/client';
import { useMe } from '@/features/account/api';
import { useSignOut } from '@/features/auth/api';
import { DevStatus } from '@/features/health/DevStatus';

function isNoResponse(error: unknown): boolean {
  return error instanceof ApiError && error.status === 0;
}

export function HomeScreen() {
  const me = useMe();
  const signOut = useSignOut();

  return (
    <ScrollView contentContainerStyle={styles.screen} contentInsetAdjustmentBehavior="automatic">
      {me.isPending && <Text style={styles.body}>Loading…</Text>}
      {me.isSuccess && <Text style={styles.body}>Signed in as {me.data.email}</Text>}
      {me.isError && (
        <>
          <Text accessibilityRole="alert" style={styles.error}>
            {errorMessage(me.error)}
          </Text>
          {isNoResponse(me.error) && <Text style={styles.hint}>You’re still signed in.</Text>}
          <Button
            title={me.isFetching ? 'Trying…' : 'Try again'}
            disabled={me.isFetching}
            onPress={() => me.refetch()}
          />
        </>
      )}

      <Button title="Log out" disabled={signOut.isPending} onPress={() => signOut.mutate()} />

      {__DEV__ && <DevStatus />}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { gap: 12, padding: 24 },
  body: { fontSize: 17 },
  error: { color: '#B00020', fontSize: 15 },
  hint: { color: '#666', fontSize: 14 },
});
