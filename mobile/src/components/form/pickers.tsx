/**
 * Choosing from a list and choosing a date, both in a sheet that slides up over the form.
 * Plain React Native views only: no native module, so no new EAS build (ADR 0012).
 */
import { type ReactNode, useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';

import {
  addMonths,
  type CalendarDate,
  formatCalendarDate,
  formatMonth,
  monthGrid,
  parseCalendarDate,
  todayLocal,
  toCalendarDate,
} from '@/lib/dates';

import { colors, spacing } from '../theme';
import { FieldShell, fieldStyles } from './fields';

type SheetProps = {
  title: string;
  visible: boolean;
  onClose: () => void;
  children: ReactNode;
};

/**
 * A bottom sheet. Tapping outside it, or Cancel, closes it without a change. A Modal is a
 * separate native root, so it gets its own safe-area provider to keep clear of the home bar.
 */
function Sheet({ title, visible, onClose, children }: SheetProps) {
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <SafeAreaProvider>
        <Pressable
          accessibilityLabel="Close"
          style={styles.backdrop}
          onPress={onClose}
          importantForAccessibility="no"
        />
        <SheetBody title={title} onClose={onClose}>
          {children}
        </SheetBody>
      </SafeAreaProvider>
    </Modal>
  );
}

function SheetBody({ title, onClose, children }: Omit<SheetProps, 'visible'>) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.l }]}>
      <View style={styles.sheetHeader}>
        <Text style={styles.sheetTitle}>{title}</Text>
        <Pressable accessibilityRole="button" onPress={onClose} hitSlop={12}>
          <Text style={styles.link}>Cancel</Text>
        </Pressable>
      </View>
      {children}
    </View>
  );
}

/** The tappable box that shows the current choice and opens the sheet. */
function PickerButton(props: {
  label: string;
  text: string;
  isPlaceholder: boolean;
  hasError: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${props.label}: ${props.text}`}
      style={[fieldStyles.box, props.hasError ? fieldStyles.boxError : null]}
      onPress={props.onPress}
    >
      <Text style={[styles.value, props.isPlaceholder ? styles.placeholder : null]}>
        {props.text}
      </Text>
      <Text style={styles.chevron}>▾</Text>
    </Pressable>
  );
}

export type SelectOption<T> = { value: T; label: string };

type SelectFieldProps<T> = {
  label: string;
  value: T;
  options: readonly SelectOption<T>[];
  onChange: (value: T) => void;
  error?: string;
  hint?: string;
};

export function SelectField<T>({
  label,
  value,
  options,
  onChange,
  error,
  hint,
}: SelectFieldProps<T>) {
  const [open, setOpen] = useState(false);
  const selected = options.find((option) => option.value === value);
  return (
    <FieldShell label={label} error={error} hint={hint}>
      <PickerButton
        label={label}
        text={selected?.label ?? 'Choose'}
        isPlaceholder={!selected}
        hasError={Boolean(error)}
        onPress={() => setOpen(true)}
      />
      <Sheet title={label} visible={open} onClose={() => setOpen(false)}>
        {options.map((option) => {
          const isSelected = option.value === value;
          return (
            <Pressable
              key={String(option.value)}
              accessibilityRole="radio"
              accessibilityState={{ selected: isSelected }}
              accessibilityLabel={option.label}
              style={styles.option}
              onPress={() => {
                onChange(option.value);
                setOpen(false);
              }}
            >
              <Text style={[styles.optionText, isSelected ? styles.selectedText : null]}>
                {option.label}
              </Text>
              {isSelected ? <Text style={styles.selectedText}>✓</Text> : null}
            </Pressable>
          );
        })}
      </Sheet>
    </FieldShell>
  );
}

type DateFieldProps = {
  label: string;
  value: CalendarDate | null;
  onChange: (value: CalendarDate | null) => void;
  error?: string;
  hint?: string;
  /** For an optional date: the words for "none", such as "No deadline". Shows a clear button. */
  noneLabel?: string;
};

/** A calendar date, kept as "YYYY-MM-DD" throughout. It never becomes a JavaScript Date. */
export function DateField({ label, value, onChange, error, hint, noneLabel }: DateFieldProps) {
  const [open, setOpen] = useState(false);
  const text = value ? formatCalendarDate(value) : (noneLabel ?? 'Choose a date');
  return (
    <FieldShell label={label} error={error} hint={hint}>
      <PickerButton
        label={label}
        text={text}
        isPlaceholder={!value}
        hasError={Boolean(error)}
        onPress={() => setOpen(true)}
      />
      <Sheet title={label} visible={open} onClose={() => setOpen(false)}>
        {open ? (
          <Calendar
            selected={value}
            onSelect={(date) => {
              onChange(date);
              setOpen(false);
            }}
          />
        ) : null}
        {noneLabel ? (
          <Pressable
            accessibilityRole="button"
            style={styles.option}
            onPress={() => {
              onChange(null);
              setOpen(false);
            }}
          >
            <Text style={styles.link}>{noneLabel}</Text>
          </Pressable>
        ) : null}
      </Sheet>
    </FieldShell>
  );
}

const WEEKDAYS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

/** One month at a time, opening on the selected date's month, or this month. */
function Calendar({
  selected,
  onSelect,
}: {
  selected: CalendarDate | null;
  onSelect: (date: CalendarDate) => void;
}) {
  const today = todayLocal();
  const start = parseCalendarDate(selected ?? today) ?? parseCalendarDate(today);
  const [shown, setShown] = useState({ year: start?.year ?? 2026, month: start?.month ?? 1 });
  const move = (delta: number) => setShown(addMonths(shown.year, shown.month, delta));

  return (
    <View>
      <View style={styles.monthHeader}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Previous month"
          hitSlop={12}
          onPress={() => move(-1)}
        >
          <Text style={styles.monthArrow}>‹</Text>
        </Pressable>
        <Text style={styles.monthTitle}>{formatMonth(shown.year, shown.month)}</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Next month"
          hitSlop={12}
          onPress={() => move(1)}
        >
          <Text style={styles.monthArrow}>›</Text>
        </Pressable>
      </View>
      <View style={styles.week}>
        {WEEKDAYS.map((letter, index) => (
          <Text key={index} style={[styles.cell, styles.weekday]}>
            {letter}
          </Text>
        ))}
      </View>
      {monthGrid(shown.year, shown.month).map((week, weekIndex) => (
        <View key={weekIndex} style={styles.week}>
          {week.map((day, index) => {
            if (day === null) {
              return <View key={index} style={styles.cell} />;
            }
            const date = toCalendarDate({ year: shown.year, month: shown.month, day });
            const isSelected = date === selected;
            return (
              <Pressable
                key={index}
                accessibilityRole="button"
                accessibilityLabel={formatCalendarDate(date)}
                accessibilityState={{ selected: isSelected }}
                style={[styles.cell, isSelected ? styles.selectedCell : null]}
                onPress={() => onSelect(date)}
              >
                <Text
                  style={[
                    styles.dayText,
                    date === today ? styles.todayText : null,
                    isSelected ? styles.selectedDayText : null,
                  ]}
                >
                  {day}
                </Text>
              </Pressable>
            );
          })}
        </View>
      ))}
      <Pressable accessibilityRole="button" style={styles.option} onPress={() => onSelect(today)}>
        <Text style={styles.link}>Today</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: { backgroundColor: 'rgba(0,0,0,0.3)', flex: 1 },
  sheet: {
    backgroundColor: colors.background,
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    paddingHorizontal: spacing.l,
    paddingTop: spacing.l,
  },
  sheetHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.s,
  },
  sheetTitle: { color: colors.text, fontSize: 17, fontWeight: '600' },
  link: { color: colors.accent, fontSize: 17 },
  value: { color: colors.text, flex: 1, fontSize: 17 },
  placeholder: { color: colors.muted },
  chevron: { color: colors.muted, fontSize: 14 },
  option: {
    alignItems: 'center',
    borderBottomColor: colors.border,
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 14,
  },
  optionText: { color: colors.text, fontSize: 17 },
  selectedText: { color: colors.accent, fontSize: 17, fontWeight: '600' },
  monthHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: spacing.s,
  },
  monthTitle: { color: colors.text, fontSize: 17, fontWeight: '600' },
  monthArrow: { color: colors.accent, fontSize: 28, paddingHorizontal: spacing.m },
  week: { flexDirection: 'row' },
  cell: { alignItems: 'center', flex: 1, height: 40, justifyContent: 'center' },
  weekday: { color: colors.muted, fontSize: 13, lineHeight: 40, textAlign: 'center' },
  dayText: { color: colors.text, fontSize: 16 },
  todayText: { color: colors.accent, fontWeight: '700' },
  selectedCell: { backgroundColor: colors.accent, borderRadius: 20 },
  selectedDayText: { color: colors.onAccent, fontWeight: '700' },
});
