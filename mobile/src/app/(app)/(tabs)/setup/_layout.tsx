import { Stack } from 'expo-router';

export default function SetupLayout() {
  return (
    <Stack>
      <Stack.Screen name="index" options={{ title: 'Setup' }} />
      <Stack.Screen name="balance" options={{ title: 'Current balance' }} />
      <Stack.Screen name="income/index" options={{ title: 'Income' }} />
      <Stack.Screen name="income/new" options={{ title: 'Add income' }} />
      <Stack.Screen name="income/[id]" options={{ title: 'Edit income' }} />
      <Stack.Screen name="bills/index" options={{ title: 'Bills' }} />
      <Stack.Screen name="bills/new" options={{ title: 'Add bill' }} />
      <Stack.Screen name="bills/[id]" options={{ title: 'Edit bill' }} />
      <Stack.Screen name="essentials/index" options={{ title: 'Essentials' }} />
      <Stack.Screen name="essentials/new" options={{ title: 'Add essential' }} />
      <Stack.Screen name="essentials/[id]" options={{ title: 'Edit essential' }} />
      <Stack.Screen name="debts/index" options={{ title: 'Debts' }} />
      <Stack.Screen name="debts/new" options={{ title: 'Add debt' }} />
      <Stack.Screen name="debts/[id]" options={{ title: 'Edit debt' }} />
      <Stack.Screen name="goals/index" options={{ title: 'Goals' }} />
      <Stack.Screen name="goals/new" options={{ title: 'Add goal' }} />
      <Stack.Screen name="goals/[id]" options={{ title: 'Edit goal' }} />
    </Stack>
  );
}
