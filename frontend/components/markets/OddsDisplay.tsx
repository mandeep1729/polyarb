'use client';

import { useOddsFormat } from '@/lib/contexts/OddsFormatContext';
import { formatOdds } from '@/lib/utils/odds';
import { cn } from '@/lib/utils/format';

interface OddsDisplayProps {
  probability: number;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

export default function OddsDisplay({
  probability,
  className,
  size = 'md',
}: OddsDisplayProps) {
  const { oddsFormat } = useOddsFormat();
  const formatted = formatOdds(probability, oddsFormat);

  const color =
    probability >= 0.7
      ? 'text-emerald-400'
      : probability >= 0.4
        ? 'text-gray-200'
        : 'text-red-400';

  const sizeClass =
    size === 'lg'
      ? 'text-2xl font-bold'
      : size === 'sm'
        ? 'text-xs font-medium'
        : 'text-sm font-semibold';

  return (
    <span className={cn(color, sizeClass, className)}>{formatted}</span>
  );
}
