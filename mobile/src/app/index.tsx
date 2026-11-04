/** Temporary dev screen: proves the phone can reach the local backend. Replaced in 3B. */
import { Stack } from 'expo-router';
import { Button, StyleSheet, Text, View } from 'react-native';

import { API_BASE_URL } from '@/api/config';
import { useHealth } from '@/features/health/api';

export default function DevHealthScreen() {
  const health = useHealth();
  return (
    <View style={styles.screen}>
      <Stack.Screen options={{ title: 'Backend connection' }} />
      <Text style={styles.label}>API address</Text>
      <Text style={styles.value}>{API_BASE_URL}</Text>
      {health.isPending && <Text style={styles.value}>Checking…</Text>}
      {health.isError && (
        <>
          <Text style={styles.label}>Could not connect</Text>
          <Text style={styles.value}>{health.error.message}</Text>
        </>
      )}
      {health.isSuccess && (
        <>
          <Text style={styles.label}>Status</Text>
          <Text style={styles.value}>{health.data.status}</Text>
          <Text style={styles.label}>Engine version</Text>
          <Text style={styles.value}>{health.data.engine_version}</Text>
        </>
      )}
      <Button
        title={health.isFetching ? 'Checking…' : 'Check again'}
        disabled={health.isFetching}
        onPress={() => health.refetch()}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, gap: 8, padding: 24 },
  label: { color: '#666', fontSize: 14, marginTop: 12 },
  value: { fontSize: 18 },
});
