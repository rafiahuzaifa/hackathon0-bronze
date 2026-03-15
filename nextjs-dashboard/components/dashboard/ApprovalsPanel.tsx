'use client';
import { useState } from 'react';
import { Mail, Linkedin, Twitter, Check, X, Clock } from 'lucide-react';
import type { ApprovalItem } from '@/lib/types';
import { formatDistanceToNow } from 'date-fns';

const typeIcons: Record<string, React.ReactNode> = {
  post_linkedin: <Linkedin size={14} className="text-blue-400" />,
  post_twitter:  <Twitter  size={14} className="text-sky-400" />,
  send_email:    <Mail     size={14} className="text-purple-400" />,
  default:       <Mail     size={14} className="text-gray-400" />,
};

export default function ApprovalsPanel({
  items,
  onApprove,
  onReject,
}: {
  items: ApprovalItem[];
  onApprove: (id: string) => void;
  onReject:  (id: string) => void;
}) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  const visible = items.filter(i => !dismissed.has(i.id));

  function approve(id: string) { onApprove(id); setDismissed(d => new Set([...d, id])); }
  function reject(id: string)  { onReject(id);  setDismissed(d => new Set([...d, id])); }

  return (
    <div className="rounded-xl p-5 h-full animate-fade-in"
         style={{ background: '#13141f', border: '1px solid #1e2035' }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold text-sm" style={{ color: '#f1f5f9' }}>
          Actions Needing Approval
        </h2>
        {visible.length > 0 && (
          <span className="text-xs font-bold px-2 py-0.5 rounded-full"
                style={{ background: 'rgba(245,158,11,0.2)', color: '#f59e0b' }}>
            {visible.length}
          </span>
        )}
      </div>

      {/* List */}
      <div className="space-y-3">
        {visible.length === 0 && (
          <p className="text-sm text-center py-8" style={{ color: '#374151' }}>
            ✅ All clear — no pending approvals
          </p>
        )}
        {visible.map((item) => (
          <ApprovalCard key={item.id} item={item} onApprove={approve} onReject={reject} />
        ))}
      </div>
    </div>
  );
}

function ApprovalCard({
  item, onApprove, onReject,
}: {
  item: ApprovalItem;
  onApprove: (id: string) => void;
  onReject:  (id: string) => void;
}) {
  const icon = typeIcons[item.type] ?? typeIcons.default;
  const timeAgo = formatDistanceToNow(new Date(item.createdAt), { addSuffix: true });

  return (
    <div className="rounded-lg p-3 card-hover"
         style={{ background: '#0d0e1a', border: '1px solid #1e2035' }}>
      <div className="flex items-start gap-3">
        {/* Type icon */}
        <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
             style={{ background: '#1a1b2e' }}>
          {icon}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5 flex-wrap">
            <code className="text-xs font-mono" style={{ color: '#94a3b8' }}>
              {item.type}
            </code>
            <RiskBadge risk={item.risk} />
          </div>
          <p className="text-sm mb-1 truncate" style={{ color: '#e2e8f0' }}>
            {item.description.slice(0, 60)}{item.description.length > 60 ? '…' : ''}
          </p>
          <div className="flex items-center gap-1" style={{ color: '#374151' }}>
            <Clock size={10} />
            <span className="text-xs">{timeAgo}</span>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2 mt-3">
        <button
          onClick={() => onApprove(item.id)}
          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-semibold transition-all hover:opacity-90"
          style={{ background: 'rgba(16,185,129,0.15)', color: '#10b981', border: '1px solid rgba(16,185,129,0.3)' }}
        >
          <Check size={12} /> Approve
        </button>
        <button
          onClick={() => onReject(item.id)}
          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-semibold transition-all hover:opacity-90"
          style={{ background: 'rgba(239,68,68,0.1)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.25)' }}
        >
          <X size={12} /> Reject
        </button>
      </div>
    </div>
  );
}

function RiskBadge({ risk }: { risk: 'low' | 'medium' | 'high' }) {
  const styles = {
    low:    { bg: 'rgba(16,185,129,0.15)',  color: '#10b981', label: 'LOW RISK' },
    medium: { bg: 'rgba(245,158,11,0.15)',  color: '#f59e0b', label: 'MEDIUM RISK' },
    high:   { bg: 'rgba(239,68,68,0.15)',   color: '#ef4444', label: 'HIGH RISK' },
  }[risk];
  return (
    <span className="text-xs font-bold px-1.5 py-0.5 rounded"
          style={{ background: styles.bg, color: styles.color }}>
      {styles.label}
    </span>
  );
}
