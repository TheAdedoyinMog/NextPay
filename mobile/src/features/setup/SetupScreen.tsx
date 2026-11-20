/** The Setup tab: every part of the user's money setup, and their account. */
import type { UseQueryResult } from '@tanstack/react-query';
import { type Href, useRouter } from 'expo-router';
import { Text } from 'react-native';

import { ActionButton } from '@/components/form';
import { ErrorState, ListRow, Screen, SectionTitle } from '@/components/screens';
import { useMe } from '@/features/account/api';
import { useSignOut } from '@/features/auth/api';
import { currentBalance, useBalanceSnapshots } from '@/features/balance/api';
import { useBills } from '@/features/bills/api';
import { useDebts } from '@/features/debts/api';
import { useEssentials } from '@/features/essentials/api';
import { useGoals } from '@/features/goals/api';
import { DevStatus } from '@/features/health/DevStatus';
import { useIncomeSources } from '@/features/income/api';
import { formatCents } from '@/lib/formatCents';

/** "3", or nothing while loading or after an error (the list screen shows those). */
function count(query: UseQueryResult<unknown[]>): string | undefined {
  return query.isSuccess ? String(query.data.length) : undefined;
}

export function SetupScreen() {
  const router = useRouter();
  const income = useIncomeSources();
  const balance = useBalanceSnapshots();
  const bills = useBills();
  const essentials = useEssentials();
  const debts = useDebts();
  const goals = useGoals();
  const current = balance.isSuccess ? currentBalance(balance.data) : null;
  const rows: { title: string; detail?: string; href: Href }[] = [
    { title: 'Income', detail: count(income), href: '/setup/income' },
    {
      title: 'Current balance',
      detail: balance.isSuccess
        ? current
          ? formatCents(current.amount_cents)
          : 'Not set'
        : undefined,
      href: '/setup/balance',
    },
    { title: 'Bills', detail: count(bills), href: '/setup/bills' },
    { title: 'Essentials', detail: count(essentials), href: '/setup/essentials' },
    { title: 'Debts', detail: count(debts), href: '/setup/debts' },
    { title: 'Goals', detail: count(goals), href: '/setup/goals' },
  ];

  return (
    <Screen>
      {rows.map((row) => (
        <ListRow
          key={row.title}
          title={row.title}
          detail={row.detail}
          onPress={() => router.push(row.href)}
        />
      ))}
      <Account />
      {__DEV__ ? <DevStatus /> : null}
    </Screen>
  );
}

function Account() {
  const me = useMe();
  const signOut = useSignOut();
  return (
    <>
      <SectionTitle>Account</SectionTitle>
      {me.isSuccess ? <Text>Signed in as {me.data.email}</Text> : null}
      {me.isError ? (
        <ErrorState error={me.error} isRetrying={me.isFetching} onRetry={() => me.refetch()} />
      ) : null}
      <ActionButton
        title="Log out"
        variant="secondary"
        disabled={signOut.isPending}
        onPress={() => signOut.mutate()}
      />
    </>
  );
}
