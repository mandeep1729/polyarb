'use client';

import { LineChart, Line, ResponsiveContainer } from 'recharts';
import type { PriceSnapshot } from '@/lib/types';

interface SparklineChartProps {
  data: PriceSnapshot[];
  width?: number;
  height?: number;
}

export default function SparklineChart({
  data,
  width = 80,
  height = 30,
}: SparklineChartProps) {
  if (!data || data.length < 2) {
    return (
      <div
        style={{ width, height }}
        className="flex items-center justify-center rounded bg-gray-800/50 text-[10px] text-gray-600"
      >
        --
      </div>
    );
  }

  const chartData = data.map((s) => ({
    price: Object.values(s.outcome_prices)[0] ?? 0,
  }));

  const firstPrice = chartData[0].price;
  const lastPrice = chartData[chartData.length - 1].price;
  const isUp = lastPrice >= firstPrice;

  return (
    <div style={{ width, height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <Line
            type="monotone"
            dataKey="price"
            stroke={isUp ? '#10b981' : '#ef4444'}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
