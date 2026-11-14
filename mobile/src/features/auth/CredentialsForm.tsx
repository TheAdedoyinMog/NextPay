import { type ReactNode, useState } from 'react';
import {
  Button,
  KeyboardAvoidingView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { errorMessage } from '@/api/client';

import type { Credentials } from './api';

type Props = {
  submitLabel: string;
  /** Sign-up: lets iOS suggest a strong password, and shows the policy. */
  isNewPassword: boolean;
  isPending: boolean;
  /** The last failed attempt, shown as the backend worded it. */
  error: unknown;
  onSubmit: (credentials: Credentials) => void;
  /** Shown above the form, such as "Your session has ended." */
  notice?: string;
  children?: ReactNode;
};

/** Email and password, shared by sign-in and sign-up. Validation is the backend's job. */
export function CredentialsForm(props: Props) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const canSubmit = email.length > 0 && password.length > 0 && !props.isPending;
  const submit = () => {
    if (canSubmit) {
      props.onSubmit({ email, password });
    }
  };

  return (
    <KeyboardAvoidingView style={styles.fill} behavior="padding">
      <ScrollView
        contentContainerStyle={styles.form}
        contentInsetAdjustmentBehavior="automatic"
        keyboardShouldPersistTaps="handled"
      >
        {props.notice ? <Text style={styles.notice}>{props.notice}</Text> : null}

        <Text style={styles.label}>Email</Text>
        <TextInput
          accessibilityLabel="Email"
          style={styles.input}
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          autoComplete="email"
          autoCorrect={false}
          keyboardType="email-address"
          textContentType="username"
          returnKeyType="next"
        />

        <Text style={styles.label}>Password</Text>
        <TextInput
          accessibilityLabel="Password"
          style={styles.input}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoCapitalize="none"
          autoComplete={props.isNewPassword ? 'new-password' : 'current-password'}
          textContentType={props.isNewPassword ? 'newPassword' : 'password'}
          returnKeyType="go"
          onSubmitEditing={submit}
        />
        {props.isNewPassword ? <Text style={styles.hint}>12 to 128 characters.</Text> : null}

        {props.error ? (
          <Text accessibilityRole="alert" style={styles.error}>
            {errorMessage(props.error)}
          </Text>
        ) : null}

        <View style={styles.submit}>
          <Button
            title={props.isPending ? 'Please wait…' : props.submitLabel}
            disabled={!canSubmit}
            onPress={submit}
          />
        </View>
        {props.children}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  form: { gap: 8, padding: 24 },
  notice: { backgroundColor: '#FFF4E5', borderRadius: 8, color: '#663C00', padding: 12 },
  label: { color: '#444', fontSize: 14, marginTop: 12 },
  input: {
    borderColor: '#CCC',
    borderRadius: 8,
    borderWidth: StyleSheet.hairlineWidth,
    fontSize: 17,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  hint: { color: '#666', fontSize: 13 },
  error: { color: '#B00020', fontSize: 15, marginTop: 8 },
  submit: { marginTop: 16 },
});
