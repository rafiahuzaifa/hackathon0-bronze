'use client';
import type { DashboardStats } from '@/lib/types';

export default function HeroCard({ stats }: { stats: DashboardStats }) {
  return (
    <div
      className="rounded-xl p-5 flex items-center justify-between gap-6 animate-fade-in"
      style={{
        background: 'linear-gradient(135deg, #13141f 0%, #1a1b2e 100%)',
        border: '1px solid #1e2035',
        boxShadow: '0 4px 24px rgba(0,0,0,0.3)',
      }}
    >
      {/* Left — Status */}
      <div className="flex items-center gap-4">
        <div className="text-4xl select-none">🤖</div>
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-xl font-bold" style={{ color: '#f1f5f9' }}>
              AI Employee is Active
            </h1>
            <span className="text-xs font-bold px-2.5 py-1 rounded-full"
                  style={{ background: 'rgba(16,185,129,0.2)', color: '#10b981', border: '1px solid rgba(16,185,129,0.3)' }}>
              {stats.botsOnline}/{stats.botsTotal} Active
            </span>
          </div>
          <p className="text-sm" style={{ color: '#64748b' }}>
            {stats.botsOnline} bots working&nbsp;•&nbsp;
            {stats.approvalsCount} approvals waiting&nbsp;•&nbsp;
            {stats.inboxCount} new tasks in inbox
          </p>
        </div>
      </div>

      {/* Right — Stat boxes */}
      <div className="flex items-center gap-1 flex-shrink-0">
        <StatBox value={stats.tasksDone.toString()} label="Tasks Done"  color="#f1f5f9" />
        <div style={{ width: 1, height: 40, background: '#1e2035' }} />
        <StatBox value={stats.inboxCount.toString()} label="Inbox"      color="#f59e0b" />
        <div style={{ width: 1, height: 40, background: '#1e2035' }} />
        <StatBox value={stats.approvalsCount.toString()} label="Approvals" color="#f59e0b" />
      </div>
    </div>
  );
}

function StatBox({ value, label, color }: { value: string; label: string; color: string }) {
  return (
    <div className="px-6 text-center">
      <div className="text-2xl font-bold leading-none mb-1" style={{ color }}>{value}</div>
      <div className="text-xs" style={{ color: '#64748b' }}>{label}</div>
    </div>
  );
}
