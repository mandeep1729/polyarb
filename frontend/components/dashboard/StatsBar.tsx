'use client';

import { useEffect, useState } from 'react';
import { Activity, BarChart3, GitCompareArrows, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils/format';

interface Stat {
  label: string;
  value: number;
  displayValue: string;
  icon: React.ReactNode;
}

interface StatsBarProps {
  totalMarkets: number;
  activePlatforms: number;
  arbOpportunities: number;
  avgSpread: number;
}

function AnimatedCounter({
  target,
  displayValue,
}: {
  target: number;
  displayValue: string;
}) {
  const [current, setCurrent] = useState(0);

  useEffect(() => {
    if (target === 0) {
      setCurrent(0);
      return;
    }
    const duration = 1000;
    const steps = 30;
    const increment = target / steps;
    let step = 0;

    const timer = setInterval(() => {
      step++;
      if (step >= steps) {
        setCurrent(target);
        clearInterval(timer);
      } else {
        setCurrent(Math.floor(increment * step));
      }
    }, duration / steps);

    return () => clearInterval(timer);
  }, [target]);

  // If we've reached the target, show the display value for proper formatting
  if (current >= target) {
    return <span>{displayValue}</span>;
  }

  return <span>{current.toLocaleString()}</span>;
}

export default function StatsBar({
  totalMarkets,
  activePlatforms,
  arbOpportunities,
  avgSpread,
}: StatsBarProps) {
  const stats: Stat[] = [
    {
      label: 'Total Markets',
      value: totalMarkets,
      displayValue: totalMarkets.toLocaleString(),
      icon: <BarChart3 className="h-5 w-5 text-emerald-500" />,
    },
    {
      label: 'Active Platforms',
      value: activePlatforms,
      displayValue: activePlatforms.toString(),
      icon: <Activity className="h-5 w-5 text-blue-500" />,
    },
    {
      label: 'Arb Opportunities',
      value: arbOpportunities,
      displayValue: arbOpportunities.toLocaleString(),
      icon: <GitCompareArrows className="h-5 w-5 text-purple-500" />,
    },
    {
      label: 'Avg Spread',
      value: avgSpread,
      displayValue: `${avgSpread.toFixed(1)}%`,
      icon: <TrendingUp className="h-5 w-5 text-amber-500" />,
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {stats.map((stat) => (
        <div
          key={stat.label}
          className="rounded-xl border border-gray-800 bg-gray-900 p-4"
        >
          <div className="mb-2 flex items-center gap-2">
            {stat.icon}
            <span className="text-xs font-medium text-gray-500">
              {stat.label}
            </span>
          </div>
          <div className="text-2xl font-bold text-gray-100">
            <AnimatedCounter
              target={stat.value}
              displayValue={stat.displayValue}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
