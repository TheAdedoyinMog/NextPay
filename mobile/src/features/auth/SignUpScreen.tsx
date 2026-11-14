import { Link } from 'expo-router';
import { StyleSheet } from 'react-native';

import { useSignUp } from './api';
import { CredentialsForm } from './CredentialsForm';

export function SignUpScreen() {
  const signUp = useSignUp();

  return (
    <CredentialsForm
      submitLabel="Create account"
      isNewPassword
      isPending={signUp.isPending}
      error={signUp.error}
      onSubmit={(credentials) => signUp.mutate(credentials)}
    >
      <Link href="/sign-in" replace style={styles.link}>
        Already have an account? Sign in
      </Link>
    </CredentialsForm>
  );
}

const styles = StyleSheet.create({
  link: { color: '#208AEF', fontSize: 16, marginTop: 24, textAlign: 'center' },
});
