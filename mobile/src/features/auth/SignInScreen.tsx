import { Link } from 'expo-router';
import { StyleSheet } from 'react-native';

import { useSignIn } from './api';
import { AppleSignInButton } from './AppleSignInButton';
import { CredentialsForm } from './CredentialsForm';
import { useSession } from './SessionProvider';

export function SignInScreen() {
  const signIn = useSignIn();
  const state = useSession();
  const sessionEnded = state.status === 'signedOut' && state.reason === 'ended';

  return (
    <CredentialsForm
      submitLabel="Sign in"
      isNewPassword={false}
      isPending={signIn.isPending}
      error={signIn.error}
      onSubmit={(credentials) => signIn.mutate(credentials)}
      notice={sessionEnded ? 'Your session has ended. Sign in again.' : undefined}
    >
      <AppleSignInButton />
      <Link href="/sign-up" replace style={styles.link}>
        New to NextPay? Create an account
      </Link>
    </CredentialsForm>
  );
}

const styles = StyleSheet.create({
  link: { color: '#208AEF', fontSize: 16, marginTop: 24, textAlign: 'center' },
});
