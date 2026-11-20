/**
 * Calendar dates: a due date or a deadline is a day on the calendar, not an instant, so it is
 * kept as a "YYYY-MM-DD" string from the API to the screen and back.
 *
 * Never pass one to `new Date("YYYY-MM-DD")`: that reads it as midnight UTC, which is the
 * previous evening in America/Indiana, so the user would see the day before. Everything here
 * works on the year, month and day numbers instead.
 */

/** "YYYY-MM-DD". A plain string, named for what it holds. */
export type CalendarDate = string;

const MONTH_NAMES = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
] as const;

const FULL_MONTH_NAMES = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
] as const;

export interface DateParts {
  year: number;
  /** 1 to 12. */
  month: number;
  day: number;
}

function isLeapYear(year: number): boolean {
  return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
}

/** 28 to 31. `month` is 1 to 12. */
export function daysInMonth(year: number, month: number): number {
  if (month === 2) {
    return isLeapYear(year) ? 29 : 28;
  }
  return [4, 6, 9, 11].includes(month) ? 30 : 31;
}

/** 0 is Sunday. Sakamoto's method: integer arithmetic only, no Date. */
export function weekdayOf({ year, month, day }: DateParts): number {
  const offsets = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4];
  const y = month < 3 ? year - 1 : year;
  const offset = offsets[month - 1] ?? 0;
  return (y + Math.floor(y / 4) - Math.floor(y / 100) + Math.floor(y / 400) + offset + day) % 7;
}

const pad = (n: number, width: number) => String(n).padStart(width, '0');

export function toCalendarDate({ year, month, day }: DateParts): CalendarDate {
  return `${pad(year, 4)}-${pad(month, 2)}-${pad(day, 2)}`;
}

/** The parts of a real date such as "2026-02-28"; null for anything else, like "2026-02-30". */
export function parseCalendarDate(text: string): DateParts | null {
  const match = /^([0-9]{4})-([0-9]{2})-([0-9]{2})$/.exec(text);
  if (!match) {
    return null;
  }
  const [year, month, day] = match.slice(1).map(Number) as [number, number, number];
  if (month < 1 || month > 12 || day < 1 || day > daysInMonth(year, month)) {
    return null;
  }
  return { year, month, day };
}

function partsOf(date: CalendarDate): DateParts {
  const parts = parseCalendarDate(date);
  if (!parts) {
    throw new RangeError(`not a calendar date: ${JSON.stringify(date)}`);
  }
  return parts;
}

/**
 * Today on this phone's calendar. Reads the local fields of the current instant, which is the
 * one correct way to turn an instant into a calendar date here.
 */
export function todayLocal(now: Date = new Date()): CalendarDate {
  return toCalendarDate({ year: now.getFullYear(), month: now.getMonth() + 1, day: now.getDate() });
}

/** "Nov 19, 2026". */
export function formatCalendarDate(date: CalendarDate): string {
  const { year, month, day } = partsOf(date);
  return `${MONTH_NAMES[month - 1]} ${day}, ${year}`;
}

/** "November 2026", for a calendar's heading. */
export function formatMonth(year: number, month: number): string {
  return `${FULL_MONTH_NAMES[month - 1]} ${year}`;
}

/** The month `delta` months from year/month: (2026, 12) + 1 is (2027, 1). */
export function addMonths(
  year: number,
  month: number,
  delta: number,
): { year: number; month: number } {
  const index = year * 12 + (month - 1) + delta;
  return { year: Math.floor(index / 12), month: (index % 12) + 1 };
}

/**
 * The days of a month laid out in weeks starting on Sunday, with null for the blanks before
 * the 1st and after the last day. Each week has seven entries.
 */
export function monthGrid(year: number, month: number): (number | null)[][] {
  const blanks = weekdayOf({ year, month, day: 1 });
  const cells: (number | null)[] = Array.from({ length: blanks }, () => null);
  for (let day = 1; day <= daysInMonth(year, month); day += 1) {
    cells.push(day);
  }
  while (cells.length % 7 !== 0) {
    cells.push(null);
  }
  const weeks: (number | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) {
    weeks.push(cells.slice(i, i + 7));
  }
  return weeks;
}

/** "1st", "2nd", "3rd", "11th", "22nd": for paydays and due days of the month. */
export function ordinal(day: number): string {
  const lastTwo = day % 100;
  if (lastTwo >= 11 && lastTwo <= 13) {
    return `${day}th`;
  }
  const suffix = { 1: 'st', 2: 'nd', 3: 'rd' }[day % 10] ?? 'th';
  return `${day}${suffix}`;
}

/**
 * An instant from the API, such as a balance's `as_of`, in this phone's time: "Nov 19, 2026,
 * 3:42 PM". Unlike a calendar date, an instant must go through Date to reach local time.
 */
export function formatInstant(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) {
    throw new RangeError(`not an instant: ${JSON.stringify(iso)}`);
  }
  const hours = at.getHours();
  const clock = `${hours % 12 === 0 ? 12 : hours % 12}:${pad(at.getMinutes(), 2)} ${hours < 12 ? 'AM' : 'PM'}`;
  return `${formatCalendarDate(todayLocal(at))}, ${clock}`;
}
