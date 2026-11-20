import {
  addMonths,
  daysInMonth,
  formatCalendarDate,
  formatInstant,
  formatMonth,
  monthGrid,
  ordinal,
  parseCalendarDate,
  todayLocal,
  toCalendarDate,
  weekdayOf,
} from './dates';

describe('the test time zone', () => {
  it('is America/Indiana, so a UTC slip shows up as the wrong day', () => {
    // jest.globalSetup.js sets it. 03:30 UTC on the 20th is 22:30 on the 19th in Indiana.
    expect(new Date('2026-11-20T03:30:00Z').getDate()).toBe(19);
    // The bug these helpers avoid: a date-only string is read as UTC midnight.
    expect(new Date('2026-11-20').getDate()).toBe(19);
  });
});

describe('formatCalendarDate', () => {
  it('shows the day that was stored, not the day before', () => {
    expect(formatCalendarDate('2026-11-20')).toBe('Nov 20, 2026');
    expect(formatCalendarDate('2027-01-01')).toBe('Jan 1, 2027');
    expect(formatCalendarDate('2024-02-29')).toBe('Feb 29, 2024');
  });

  it('refuses something that is not a calendar date', () => {
    expect(() => formatCalendarDate('2026-11-20T00:00:00Z')).toThrow(RangeError);
  });
});

describe('todayLocal', () => {
  it('uses the phone’s calendar near midnight UTC', () => {
    // Late evening in Indiana is already tomorrow in UTC.
    expect(todayLocal(new Date('2026-11-20T03:30:00Z'))).toBe('2026-11-19');
    expect(todayLocal(new Date('2026-11-20T04:59:59Z'))).toBe('2026-11-19');
    expect(todayLocal(new Date('2026-11-20T05:00:00Z'))).toBe('2026-11-20');
  });

  it('crosses a year end the same way', () => {
    expect(todayLocal(new Date('2027-01-01T02:00:00Z'))).toBe('2026-12-31');
  });
});

describe('parseCalendarDate', () => {
  it('reads real dates', () => {
    expect(parseCalendarDate('2026-11-19')).toEqual({ year: 2026, month: 11, day: 19 });
    expect(parseCalendarDate('2024-02-29')).toEqual({ year: 2024, month: 2, day: 29 });
  });

  it.each(['2026-02-29', '2026-02-30', '2026-13-01', '2026-00-10', '2026-1-5', '', 'tomorrow'])(
    'rejects %p',
    (text) => {
      expect(parseCalendarDate(text)).toBeNull();
    },
  );

  it('round-trips with toCalendarDate', () => {
    expect(toCalendarDate({ year: 2027, month: 3, day: 5 })).toBe('2027-03-05');
  });
});

describe('calendar arithmetic', () => {
  it.each([
    [2026, 2, 28],
    [2024, 2, 29],
    [1900, 2, 28],
    [2000, 2, 29],
    [2026, 4, 30],
    [2026, 12, 31],
  ])('%d-%d has %d days', (year, month, days) => {
    expect(daysInMonth(year, month)).toBe(days);
  });

  it.each([
    ['2026-11-19', 4], // Thursday
    ['2026-11-01', 0], // Sunday
    ['2024-02-29', 4],
    ['2000-01-01', 6],
    ['2027-03-01', 1],
  ])('%s falls on weekday %d', (date, weekday) => {
    const parts = parseCalendarDate(date);
    expect(parts && weekdayOf(parts)).toBe(weekday);
  });

  it('moves between months across year ends', () => {
    expect(addMonths(2026, 12, 1)).toEqual({ year: 2027, month: 1 });
    expect(addMonths(2026, 1, -1)).toEqual({ year: 2025, month: 12 });
    expect(addMonths(2026, 11, 0)).toEqual({ year: 2026, month: 11 });
  });

  it('lays out a month in Sunday-first weeks', () => {
    const weeks = monthGrid(2026, 11); // starts on a Sunday, 30 days
    expect(weeks).toHaveLength(5);
    expect(weeks[0]).toEqual([1, 2, 3, 4, 5, 6, 7]);
    expect(weeks[4]).toEqual([29, 30, null, null, null, null, null]);
    const february = monthGrid(2027, 2); // starts on a Monday
    expect(february[0]?.[0]).toBeNull();
    expect(february[0]?.[1]).toBe(1);
  });

  it('names months and days', () => {
    expect(formatMonth(2026, 11)).toBe('November 2026');
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 31].map(ordinal)).toEqual([
      '1st',
      '2nd',
      '3rd',
      '4th',
      '11th',
      '12th',
      '13th',
      '21st',
      '22nd',
      '23rd',
      '31st',
    ]);
  });
});

describe('formatInstant', () => {
  it('shows an instant in local time, which can be the previous calendar day', () => {
    expect(formatInstant('2026-11-20T03:30:00Z')).toBe('Nov 19, 2026, 10:30 PM');
    expect(formatInstant('2026-11-20T17:05:00Z')).toBe('Nov 20, 2026, 12:05 PM');
    expect(formatInstant('2026-11-20T05:00:00+00:00')).toBe('Nov 20, 2026, 12:00 AM');
  });

  it('refuses garbage', () => {
    expect(() => formatInstant('soon')).toThrow(RangeError);
  });
});
