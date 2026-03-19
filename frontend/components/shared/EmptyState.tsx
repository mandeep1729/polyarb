import { Inbox } from 'lucide-react';
import type { ReactNode } from 'react';

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
}

export default function EmptyState({
  icon,
  title,
  description,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="mb-4 text-gray-600">
        {icon ?? <Inbox className="h-12 w-12" />}
      </div>
      <h3 className="mb-1 text-lg font-semibold text-gray-300">{title}</h3>
      {description && (
        <p className="max-w-sm text-sm text-gray-500">{description}</p>
      )}
    </div>
  );
}
