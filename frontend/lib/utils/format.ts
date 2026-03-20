import { formatDistanceToNowStrict, differenceInHours, differenceInMinutes, isPast } from 'date-fns';

export function formatVolume(n: number): string {
  if (n >= 1_000_000_000) {
    return `$${(n / 1_000_000_000).toFixed(1)}B`;
  }
  if (n >= 1_000_000) {
    return `$${(n / 1_000_000).toFixed(1)}M`;
  }
  if (n >= 1_000) {
    return `$${(n / 1_000).toFixed(0)}K`;
  }
  return `$${n.toLocaleString()}`;
}

export function formatLiquidity(n: number): 'high' | 'medium' | 'low' {
  if (n >= 100_000) return 'high';
  if (n >= 10_000) return 'medium';
  return 'low';
}

export function formatTimeRemaining(endDate: string): string {
  const end = new Date(endDate);
  if (isPast(end)) return 'Expired';

  const now = new Date();
  const hoursLeft = differenceInHours(end, now);
  const minutesLeft = differenceInMinutes(end, now);

  if (hoursLeft >= 48) {
    const days = Math.floor(hoursLeft / 24);
    const remainingHours = hoursLeft % 24;
    return `${days}d ${remainingHours}h`;
  }
  if (hoursLeft >= 1) {
    const remainingMinutes = minutesLeft % 60;
    return `${hoursLeft}h ${remainingMinutes}m`;
  }
  return `${minutesLeft}m`;
}

export function cn(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(' ');
}
