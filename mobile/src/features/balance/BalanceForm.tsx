/** Entering what's in the account right now. Used on the balance screen and in onboarding. */
import { type ReactNode, useState } from 'react';

import { ActionButton, FormError, formErrors, mergeErrors, MoneyField } from '@/components/form';
import { parseMoney } from '@/lib/money';

type Props = {
  submitLabel: string;
  /** What the field starts with, such as the last balance as text. */
  initialText?: string;
  label?: string;
  hint?: string;
  isPending: boolean;
  error: unknown;
  onSubmit: (amountCents: number) => void;
  children?: ReactNode;
};

export function BalanceForm({
  submitLabel,
  initialText = '',
  label = 'Available balance',
  hint = "What your account shows right now. Use a minus sign if it's overdrawn.",
  isPending,
  error,
  onSubmit,
  children,
}: Props) {
  const [amount, setAmount] = useState(initialText);
  const [local, setLocal] = useState<{ amount?: string }>({});
  const shown = mergeErrors(local, formErrors(error, { amount_cents: 'amount' }));
  const submit = () => {
    const parsed = parseMoney(amount, { allowNegative: true });
    setLocal(parsed.ok ? {} : { amount: parsed.message });
    if (parsed.ok) {
      onSubmit(parsed.cents);
    }
  };

  return (
    <>
      <MoneyField
        label={label}
        value={amount}
        onChangeText={setAmount}
        allowNegative
        hint={hint}
        error={shown.fields.amount}
      />
      <FormError message={shown.form} />
      <ActionButton title={submitLabel} isPending={isPending} onPress={submit} />
      {children}
    </>
  );
}
