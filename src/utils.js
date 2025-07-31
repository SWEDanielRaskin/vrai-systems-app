import { format, isToday, isYesterday, differenceInDays } from 'date-fns';

/**
 * Formats a timestamp smartly:
 * - Today: time only
 * - Yesterday: 'Yesterday, time'
 * - 2+ days ago: 'X days ago, time'
 * - >7 days: 'MMM d, yyyy, time'
 */
export function formatSmartTimestamp(timestamp) {
  try {
    const date = new Date(timestamp);
    if (isNaN(date)) return timestamp;
    const now = new Date();

    if (isToday(date)) {
      return format(date, 'p'); // e.g., '3:00 PM'
    }
    if (isYesterday(date)) {
      return `Yesterday, ${format(date, 'p')}`;
    }
    const daysAgo = differenceInDays(now, date);
    if (daysAgo < 7) {
      return `${daysAgo} days ago, ${format(date, 'p')}`;
    }
    return format(date, 'MMM d, yyyy, p');
  } catch {
    return timestamp;
  }
}
