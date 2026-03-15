'use client';
import { formatDistanceToNow } from 'date-fns';
import type { ActivityEvent } from '@/lib/types';

const typeColors: Record<string, string> = {
  email: '#3b82f6', whatsapp: '#10b981', linkedin: '#3b82f6',
  twitter: '#06b6d4', bank: '#f59e0b', vault: '#8b5cf6',
  system: '#64748b', alert: '#ef4444',
};

export default function ActivityPanel({ events }: { events: ActivityEvent[] }) {
  return (
    <div className="rounded-xl p-5 h-full animate-fade-in"
         style={{ background: '#13141f', border: '1px solid #1e2035' }}>
      <h2 className="font-semibold text-sm mb-4" style={{ color: '#f1f5f9' }}>
        What Happened Today
      </h2>
      <div className="space-y-2 overflow-y-auto" style={{ maxHeight: 340 }}>
        {events.map((ev) => (
          <ActivityRow key={ev.id} event={ev} />
        ))}
      </div>
    </div>
  );
}

function ActivityRow({ event }: { event: ActivityEvent }) {
  const dotColor = event.status === 'ok' ? '#10b981' : event.status === 'warning' ? '#f59e0b' : '#ef4444';
  const timeAgo = formatDistanceToNow(new Date(event.timestamp), { addSuffix: true });

  return (
    <div className="flex items-start gap-3 py-2 border-b last:border-0 group"
         style={{ borderColor: '#1e2035' }}>
      {/* Dot */}
      <div className="mt-1.5 flex-shrink-0">
        <span className="block w-2 h-2 rounded-full" style={{ background: dotColor, boxShadow: `0 0 6px ${dotColor}66` }} />
      </div>

      {/* Message */}
      <div className="flex-1 min-w-0">
        <p className="text-xs leading-relaxed" style={{ color: '#cbd5e1' }}>
          {event.message}
        </p>
        <p className="text-xs mt-0.5" style={{ color: '#374151' }}>{timeAgo}</p>
      </div>
    </div>
  );
}
