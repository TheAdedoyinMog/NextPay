import { fireEvent, render, screen } from '@testing-library/react-native';
import { useState } from 'react';
import { Alert } from 'react-native';

import { ApiError } from '@/api/client';

import {
  ActionButton,
  confirmDelete,
  DateField,
  formErrors,
  FormError,
  mergeErrors,
  MoneyField,
  SelectField,
  TextField,
} from './index';

jest.mock('@/api/config', () => ({ API_BASE_URL: 'http://api.test' }));

describe('TextField and MoneyField', () => {
  it('labels the input and shows its error instead of its hint', async () => {
    const onChangeText = jest.fn();
    await render(
      <>
        <TextField label="Name" value="" onChangeText={onChangeText} hint="As on your payslip" />
        <MoneyField label="Amount" value="12" onChangeText={jest.fn()} error="Enter an amount." />
      </>,
    );

    await fireEvent.changeText(screen.getByLabelText('Name'), 'Acme');
    expect(onChangeText).toHaveBeenCalledWith('Acme');
    expect(screen.getByText('As on your payslip')).toBeTruthy();
    expect(screen.getByLabelText('Amount: Enter an amount.')).toBeTruthy();
    expect(screen.getByText('$')).toBeTruthy();
  });

  it('offers a minus key only where negative amounts are allowed', async () => {
    await render(
      <>
        <MoneyField label="Bill" value="" onChangeText={jest.fn()} />
        <MoneyField label="Balance" value="" onChangeText={jest.fn()} allowNegative />
      </>,
    );

    expect(screen.getByLabelText('Bill').props.keyboardType).toBe('decimal-pad');
    expect(screen.getByLabelText('Balance').props.keyboardType).toBe('numbers-and-punctuation');
  });
});

describe('SelectField', () => {
  function Repeat() {
    const [value, setValue] = useState<number | null>(1);
    return (
      <SelectField
        label="Repeats"
        value={value}
        onChange={setValue}
        options={[
          { value: null, label: 'Once' },
          { value: 1, label: 'Every month' },
          { value: 12, label: 'Every year' },
        ]}
      />
    );
  }

  it('shows the choice, and changes it from the sheet, including to null', async () => {
    await render(<Repeat />);

    await fireEvent.press(screen.getByRole('button', { name: 'Repeats: Every month' }));
    await fireEvent.press(screen.getByRole('radio', { name: 'Every year' }));
    expect(screen.getByRole('button', { name: 'Repeats: Every year' })).toBeTruthy();

    await fireEvent.press(screen.getByRole('button', { name: 'Repeats: Every year' }));
    await fireEvent.press(screen.getByRole('radio', { name: 'Once' }));
    expect(screen.getByRole('button', { name: 'Repeats: Once' })).toBeTruthy();
  });
});

describe('DateField', () => {
  function Deadline({
    initial,
    onChange,
  }: {
    initial: string | null;
    onChange: (v: string | null) => void;
  }) {
    const [value, setValue] = useState(initial);
    return (
      <DateField
        label="Deadline"
        value={value}
        noneLabel="No deadline"
        onChange={(next) => {
          setValue(next);
          onChange(next);
        }}
      />
    );
  }

  it('shows the stored date as that same day, even late in the day in Indiana', async () => {
    await render(<Deadline initial="2026-11-20" onChange={jest.fn()} />);

    expect(screen.getByRole('button', { name: 'Deadline: Nov 20, 2026' })).toBeTruthy();
  });

  it('picks a day as a YYYY-MM-DD string, across months', async () => {
    const onChange = jest.fn();
    await render(<Deadline initial="2026-11-20" onChange={onChange} />);

    await fireEvent.press(screen.getByRole('button', { name: 'Deadline: Nov 20, 2026' }));
    expect(screen.getByText('November 2026')).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Next month' }));
    expect(screen.getByText('December 2026')).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Dec 1, 2026' }));

    expect(onChange).toHaveBeenLastCalledWith('2026-12-01');
    expect(screen.getByRole('button', { name: 'Deadline: Dec 1, 2026' })).toBeTruthy();
  });

  it('can be cleared when optional', async () => {
    const onChange = jest.fn();
    await render(<Deadline initial="2027-01-31" onChange={onChange} />);

    await fireEvent.press(screen.getByRole('button', { name: 'Deadline: Jan 31, 2027' }));
    await fireEvent.press(screen.getByRole('button', { name: 'No deadline' }));

    expect(onChange).toHaveBeenLastCalledWith(null);
    expect(screen.getByRole('button', { name: 'Deadline: No deadline' })).toBeTruthy();
  });

  it('opens on today’s month when empty', async () => {
    jest.useFakeTimers({
      now: new Date('2027-03-01T03:00:00Z'),
      doNotFake: ['nextTick', 'setImmediate'],
    });
    try {
      await render(<Deadline initial={null} onChange={jest.fn()} />);

      await fireEvent.press(screen.getByRole('button', { name: 'Deadline: No deadline' }));
      // 03:00 UTC on March 1 is still February 28 in Indiana.
      expect(screen.getByText('February 2027')).toBeTruthy();
    } finally {
      jest.useRealTimers();
    }
  });
});

describe('ActionButton', () => {
  it('ignores presses while pending, and says so', async () => {
    const onPress = jest.fn();
    await render(<ActionButton title="Save" isPending onPress={onPress} />);

    const button = screen.getByRole('button', { name: 'Saving…' });
    await fireEvent.press(button);

    expect(onPress).not.toHaveBeenCalled();
    expect(button).toBeDisabled();
  });
});

describe('confirmDelete', () => {
  it('asks first, and deletes only on the destructive button', () => {
    const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
    const onConfirm = jest.fn();

    confirmDelete({ title: 'Delete Rent?', message: 'This can’t be undone.', onConfirm });

    expect(onConfirm).not.toHaveBeenCalled();
    const buttons = alert.mock.calls[0]?.[2] ?? [];
    expect(buttons.map((b) => [b.text, b.style])).toEqual([
      ['Cancel', 'cancel'],
      ['Delete', 'destructive'],
    ]);
    buttons[1]?.onPress?.();
    expect(onConfirm).toHaveBeenCalledTimes(1);
    alert.mockRestore();
  });
});

describe('formErrors', () => {
  const fieldFor = {
    name: 'name',
    expected_amount_cents: 'amount',
    anchor_date: 'anchorDate',
  } as const;

  it('is empty without an error', () => {
    expect(formErrors(null, fieldFor)).toEqual({ fields: {}, form: null });
  });

  it('puts each 422 problem next to its field, including inside a pay schedule', () => {
    const error = new ApiError(422, 'validation_error', 'Check these fields: ...', {
      name: 'String should have at least 1 character',
      'schedule.weekly.anchor_date': 'Input should be a valid date',
    });

    expect(formErrors(error, fieldFor)).toEqual({
      fields: {
        name: 'String should have at least 1 character',
        anchorDate: 'Input should be a valid date',
      },
      form: 'Check the fields marked above.',
    });
  });

  it('shows money limits in dollars, not cents', () => {
    const error = new ApiError(422, 'validation_error', '...', {
      expected_amount_cents: 'Input should be less than or equal to 100000000000',
    });

    expect(formErrors(error, fieldFor).fields.amount).toBe(
      'Input should be less than or equal to $1,000,000,000.00',
    );
  });

  it('names a field the form doesn’t show, rather than hiding it', () => {
    const error = new ApiError(422, 'validation_error', '...', {
      surprise: 'Extra inputs are not permitted',
    });

    expect(formErrors(error, fieldFor)).toEqual({
      fields: {},
      form: 'Check these fields: surprise',
    });
  });

  it('shows any other error for the whole form, in friendly words for a 5xx', () => {
    expect(
      formErrors(new ApiError(409, 'emergency_goal_exists', 'You already have one.'), fieldFor),
    ).toEqual({
      fields: {},
      form: 'You already have one.',
    });
    expect(
      formErrors(
        new ApiError(422, 'invalid_input', 'Pick two paydays at least 7 days apart.'),
        fieldFor,
      ).form,
    ).toBe('Pick two paydays at least 7 days apart.');
  });

  it('lets the app’s own checks win over the server’s', () => {
    const server = { fields: { amount: 'from server', name: 'name problem' }, form: 'x' };
    expect(mergeErrors({ amount: 'Enter an amount.' }, server)).toEqual({
      fields: { amount: 'Enter an amount.', name: 'name problem' },
      form: 'x',
    });
  });
});

describe('FormError', () => {
  it('renders nothing without a message, and an alert with one', async () => {
    await render(<FormError message={null} />);
    expect(screen.queryByRole('alert')).toBeNull();

    await render(<FormError message="Something went wrong on our side. Try again in a moment." />);
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Something went wrong on our side. Try again in a moment.',
    );
  });
});
