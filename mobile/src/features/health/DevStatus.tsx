/** Development only: which API the app is using, and whether it answers. */
import { Button, StyleSheet, Text, View } from 'react-native';

import { API_BASE_URL } from '@/api/config';

import { useHealth } from './api';

export function DevStatus() {
  const health = useHealth();
  return (
    <View style={styles.panel}>
      <Text style={styles.heading}>Development</Text>
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
  panel: { backgroundColor: '#F2F2F7', borderRadius: 12, gap: 4, marginTop: 32, padding: 16 },
  heading: { fontSize: 13, fontWeight: '600', textTransform: 'uppercase', color: '#666' },
  label: { color: '#666', fontSize: 13, marginTop: 8 },
  value: { fontSize: 16 },
});
