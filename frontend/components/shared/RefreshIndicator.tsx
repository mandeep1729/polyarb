'use client';

import { useIsFetching } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';

export default function RefreshIndicator() {
  const isFetching = useIsFetching();

  if (!isFetching) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex items-center gap-2 rounded-full bg-gray-800 px-3 py-1.5 text-xs text-gray-400 shadow-lg">
      <RefreshCw className="h-3 w-3 animate-spin" />
      <span>Updating</span>
    </div>
  );
}
