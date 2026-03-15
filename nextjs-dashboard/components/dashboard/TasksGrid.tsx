'use client';
import { Mail, MessageCircle, AlertTriangle, Linkedin, Twitter } from 'lucide-react';
import type { TaskFile } from '@/lib/types';
import { formatDistanceToNow } from 'date-fns';

const typeConfig = {
  EMAIL:      { icon: Mail,          color: '#3b82f6', bg: 'rgba(59,130,246,0.1)' },
  WHATSAPP:   { icon: MessageCircle, color: '#10b981', bg: 'rgba(16,185,129,0.1)' },
  BANK_ALERT: { icon: AlertTriangle, color: '#f59e0b', bg: 'rgba(245,158,11,0.1)' },
  LINKEDIN:   { icon: Linkedin,      color: '#3b82f6', bg: 'rgba(59,130,246,0.1)' },
  TWITTER:    { icon: Twitter,       color: '#06b6d4', bg: 'rgba(6,182,212,0.1)' },
  MANUAL:     { icon: Mail,          color: '#8b5cf6', bg: 'rgba(139,92,246,0.1)' },
};

const statusConfig = {
  done:        { label: 'Done',         color: '#10b981', bg: 'rgba(16,185,129,0.15)' },
  needs_review:{ label: 'Needs Review', color: '#f97316', bg: 'rgba(249,115,22,0.15)' },
  pending:     { label: 'Pending',      color: '#f59e0b', bg: 'rgba(245,158,11,0.15)' },
  in_progress: { label: 'In Progress',  color: '#3b82f6', bg: 'rgba(59,130,246,0.15)' },
};

export default function TasksGrid({ tasks }: { tasks: TaskFile[] }) {
  return (
    <div className="animate-fade-in">
      <h2 className="font-semibold text-sm mb-3" style={{ color: '#f1f5f9' }}>
        Recently Processed Tasks
      </h2>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {tasks.map((task) => (
          <TaskCard key={task.id} task={task} />
        ))}
      </div>
    </div>
  );
}

function TaskCard({ task }: { task: TaskFile }) {
  const cfg    = typeConfig[task.type] ?? typeConfig.EMAIL;
  const status = statusConfig[task.status];
  const Icon   = cfg.icon;
  const timeAgo = formatDistanceToNow(new Date(task.createdAt), { addSuffix: true });

  return (
    <div className="rounded-xl p-3 card-hover cursor-pointer"
         style={{ background: '#13141f', border: '1px solid #1e2035' }}>
      {/* Icon */}
      <div className="w-8 h-8 rounded-lg flex items-center justify-center mb-3"
           style={{ background: cfg.bg }}>
        <Icon size={15} style={{ color: cfg.color }} />
      </div>

      {/* Filename */}
      <p className="text-xs font-mono mb-2 truncate" style={{ color: '#94a3b8' }} title={task.filename}>
        {task.filename}
      </p>

      {/* Status */}
      <span className="text-xs font-semibold px-2 py-0.5 rounded-full"
            style={{ background: status.bg, color: status.color }}>
        {status.label}
      </span>

      {/* Time */}
      <p className="text-xs mt-2" style={{ color: '#374151' }}>{timeAgo}</p>
    </div>
  );
}
