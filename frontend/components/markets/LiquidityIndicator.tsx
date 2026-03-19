'use client';

import { formatLiquidity, formatVolume, cn } from '@/lib/utils/format';
import * as Tooltip from '@radix-ui/react-tooltip';

interface LiquidityIndicatorProps {
  liquidity: number | null;
  className?: string;
}

const colorMap = {
  high: 'bg-emerald-500',
  medium: 'bg-amber-500',
  low: 'bg-red-500',
};

const labelMap = {
  high: 'High Liquidity',
  medium: 'Medium Liquidity',
  low: 'Low Liquidity',
};

export default function LiquidityIndicator({
  liquidity,
  className,
}: LiquidityIndicatorProps) {
  const level = formatLiquidity(liquidity ?? 0);

  return (
    <Tooltip.Provider delayDuration={200}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <span
            className={cn(
              'inline-flex items-center gap-1.5 text-xs text-gray-400',
              className
            )}
          >
            <span
              className={cn(
                'inline-block h-2 w-2 rounded-full',
                colorMap[level]
              )}
            />
            {labelMap[level]}
          </span>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            side="top"
            className="rounded-lg bg-gray-800 px-3 py-1.5 text-xs text-gray-200 shadow-xl"
            sideOffset={4}
          >
            {formatVolume(liquidity ?? 0)}
            <Tooltip.Arrow className="fill-gray-800" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}
