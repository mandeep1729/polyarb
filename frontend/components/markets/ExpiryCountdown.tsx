'use client';

import { useState, useEffect } from 'react';
import { formatTimeRemaining, cn } from '@/lib/utils/format';
import { differenceInHours, isPast } from 'date-fns';
import { Clock } from 'lucide-react';

interface ExpiryCountdownProps {
  endDate: string | null;
  className?: string;
}

export default function ExpiryCountdown({
  endDate,
  className,
}: ExpiryCountdownProps) {
  const [display, setDisplay] = useState('');
  const [colorClass, setColorClass] = useState('text-gray-500');

  useEffect(() => {
    if (!endDate) {
      setDisplay('No expiry');
      setColorClass('text-gray-500');
      return;
    }

    function update() {
      const end = new Date(endDate!);
      if (isPast(end)) {
        setDisplay('Expired');
        setColorClass('text-gray-600');
        return;
      }
      const hours = differenceInHours(end, new Date());
      if (hours > 168) {
        setColorClass('text-emerald-500');
      } else if (hours > 24) {
        setColorClass('text-amber-500');
      } else {
        setColorClass('text-red-500');
      }
      setDisplay(formatTimeRemaining(endDate!));
    }

    update();
    const interval = setInterval(update, 60_000);
    return () => clearInterval(interval);
  }, [endDate]);

  return (
    <span className={cn('inline-flex items-center gap-1 text-xs', colorClass, className)}>
      <Clock className="h-3 w-3" />
      {display}
    </span>
  );
}
