import { formatVolume, cn } from '@/lib/utils/format';
import { BarChart3 } from 'lucide-react';

interface VolumeBarProps {
  volume: number | null;
  maxVolume?: number;
  className?: string;
}

export default function VolumeBar({
  volume,
  maxVolume = 10_000_000,
  className,
}: VolumeBarProps) {
  const vol = volume ?? 0;
  const percentage = Math.min((vol / maxVolume) * 100, 100);

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <BarChart3 className="h-3 w-3 shrink-0 text-gray-500" />
      <div className="flex flex-1 items-center gap-2">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-800">
          <div
            className="h-full rounded-full bg-emerald-600 transition-all duration-500"
            style={{ width: `${percentage}%` }}
          />
        </div>
        <span className="shrink-0 text-xs text-gray-400">
          {formatVolume(vol)}
        </span>
      </div>
    </div>
  );
}
