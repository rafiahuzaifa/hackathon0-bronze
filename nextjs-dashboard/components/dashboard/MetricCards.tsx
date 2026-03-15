'use client';
import { SparklineChart } from './SparklineChart';
import type { DashboardStats } from '@/lib/types';

const sparkData = [4,7,5,9,6,8,7,9,11,9,12,10];

export default function MetricCards({ stats }: { stats: DashboardStats }) {
  const botPercent = Math.round((stats.botsOnline / stats.botsTotal) * 100);

  return (
    <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
      {/* Bots Online */}
      <MetricCard>
        <CardLabel>BOTS ONLINE</CardLabel>
        <div className="flex items-end justify-between mb-2">
          <span className="text-3xl font-bold" style={{ color: '#f1f5f9' }}>
            {stats.botsOnline}<span className="text-lg text-[#64748b]">/{stats.botsTotal}</span>
          </span>
          <SparklineChart data={sparkData} color="#7c3aed" />
        </div>
        <p className="text-xs mb-3" style={{ color: '#64748b' }}>background workers</p>
        <div className="progress-bar h-1.5 w-full">
          <div className="progress-fill h-full" style={{ width: `${botPercent}%`, background: 'linear-gradient(90deg, #7c3aed, #3b82f6)' }} />
        </div>
        <p className="text-xs mt-1 text-right" style={{ color: '#64748b' }}>{botPercent}%</p>
      </MetricCard>

      {/* Need Approval */}
      <MetricCard>
        <CardLabel>NEED APPROVAL</CardLabel>
        <div className="flex items-center gap-3 mb-1">
          <span className="text-3xl font-bold" style={{ color: '#f59e0b' }}>{stats.approvalsCount}</span>
          <span className="text-xs px-2 py-0.5 rounded-full animate-pulse"
                style={{ background: 'rgba(245,158,11,0.15)', color: '#f59e0b' }}>
            Pending
          </span>
        </div>
        <p className="text-xs mb-3" style={{ color: '#64748b' }}>actions waiting for you</p>
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-red-500 dot-pulse" />
          <span className="text-xs" style={{ color: '#ef4444' }}>Needs attention</span>
        </div>
      </MetricCard>

      {/* Monthly Income */}
      <MetricCard>
        <CardLabel>MONTHLY INCOME</CardLabel>
        <div className="flex items-end gap-2 mb-1">
          <span className="text-2xl font-bold" style={{ color: '#10b981' }}>
            {stats.currency} {(stats.monthlyIncome / 1000).toFixed(1)}K
          </span>
          <span className="text-xs px-1.5 py-0.5 rounded mb-0.5"
                style={{ background: 'rgba(16,185,129,0.15)', color: '#10b981' }}>
            +34%
          </span>
        </div>
        <p className="text-xs mb-1" style={{ color: '#64748b' }}>from last month</p>
        <p className="text-xs" style={{ color: '#94a3b8' }}>
          Net <span className="font-semibold">{stats.currency} {((stats.monthlyIncome - stats.monthlyExpenses) / 1000).toFixed(1)}K</span>
        </p>
      </MetricCard>

      {/* Monthly Expenses */}
      <MetricCard>
        <CardLabel>MONTHLY EXPENSES</CardLabel>
        <div className="flex items-end gap-2 mb-1">
          <span className="text-2xl font-bold" style={{ color: '#ef4444' }}>
            {stats.currency} {(stats.monthlyExpenses / 1000).toFixed(1)}K
          </span>
        </div>
        <p className="text-xs mb-3" style={{ color: '#64748b' }}>this month</p>
        <div className="progress-bar h-1.5 w-full">
          <div className="progress-fill h-full" style={{
            width: `${Math.round((stats.monthlyExpenses / stats.monthlyIncome) * 100)}%`,
            background: 'linear-gradient(90deg, #ef4444, #f59e0b)'
          }} />
        </div>
        <p className="text-xs mt-1" style={{ color: '#64748b' }}>
          {Math.round((stats.monthlyExpenses / stats.monthlyIncome) * 100)}% of income
        </p>
      </MetricCard>
    </div>
  );
}

function MetricCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl p-4 card-hover animate-fade-in"
         style={{ background: '#13141f', border: '1px solid #1e2035' }}>
      {children}
    </div>
  );
}

function CardLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-xs font-semibold tracking-widest mb-3" style={{ color: '#374151' }}>
      {children}
    </p>
  );
}
