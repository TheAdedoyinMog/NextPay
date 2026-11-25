import * as AppleAuthentication from 'expo-apple-authentication';
import { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { errorMessage } from '@/api/client';

import { AppleSignInError, useAppleSignIn } from './apple';

/**
 * Apple's own button, as App Review requires, with any failure shown under it. Hidden where
 * Sign in with Apple isn't available.
 */
export function AppleSignInButton() {
  const [isAvailable, setIsAvailable] = useState(false);
  const signIn = useAppleSignIn();

  useEffect(() => {
    let active = true;
    AppleAuthentication.isAvailableAsync()
      .then((available) => active && setIsAvailable(available))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  if (!isAvailable) {
    return null;
  }
  return (
    <View style={styles.container}>
      <Text style={styles.or}>or</Text>
      <AppleAuthentication.AppleAuthenticationButton
        buttonType={AppleAuthentication.AppleAuthenticationButtonType.SIGN_IN}
        buttonStyle={AppleAuthentication.AppleAuthenticationButtonStyle.BLACK}
        cornerRadius={8}
        style={styles.button}
        onPress={() => {
          if (!signIn.isPending) {
            signIn.mutate();
          }
        }}
      />
      {signIn.error ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {signIn.error instanceof AppleSignInError
            ? signIn.error.message
            : errorMessage(signIn.error)}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 12, marginTop: 16 },
  or: { color: '#666', fontSize: 14, textAlign: 'center' },
  button: { height: 48, width: '100%' },
  error: { color: '#B00020', fontSize: 15 },
});
