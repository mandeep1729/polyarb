import { cn } from '@/lib/utils/format';

interface PlatformBadgeProps {
  platform: string;
  className?: string;
}

const platformColors: Record<string, string> = {
  polymarket: 'bg-purple-900/60 text-purple-300 border-purple-700/50',
  kalshi: 'bg-blue-900/60 text-blue-300 border-blue-700/50',
};

export default function PlatformBadge({
  platform,
  className,
}: PlatformBadgeProps) {
  const colorClass =
    platformColors[platform.toLowerCase()] ??
    'bg-gray-800 text-gray-300 border-gray-700';

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-medium capitalize',
        colorClass,
        className
      )}
    >
      {platform}
    </span>
  );
}
