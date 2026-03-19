import { cn } from '@/lib/utils/format';

interface ArbSpreadBadgeProps {
  spread: number;
  className?: string;
}

export default function ArbSpreadBadge({
  spread,
  className,
}: ArbSpreadBadgeProps) {
  const intensity =
    spread >= 10
      ? 'bg-emerald-500/30 text-emerald-300 border-emerald-500/40'
      : spread >= 5
        ? 'bg-emerald-600/20 text-emerald-400 border-emerald-600/30'
        : spread >= 2
          ? 'bg-emerald-700/15 text-emerald-400 border-emerald-700/25'
          : 'bg-emerald-900/20 text-emerald-500 border-emerald-800/20';

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-bold tabular-nums',
        intensity,
        className
      )}
    >
      +{spread.toFixed(1)}%
    </span>
  );
}
