'use client';
import { useState, useEffect, useCallback } from 'react';
import HeroCard       from '@/components/dashboard/HeroCard';
import MetricCards    from '@/components/dashboard/MetricCards';
import ApprovalsPanel from '@/components/dashboard/ApprovalsPanel';
import ActivityPanel  from '@/components/dashboard/ActivityPanel';
import TasksGrid      from '@/components/dashboard/TasksGrid';
import BotsGrid       from '@/components/dashboard/BotsGrid';
import { mockData, api } from '@/lib/api';
import type { DashboardStats, ApprovalItem, ActivityEvent, TaskFile, BotStatus } from '@/lib/types';
import { useWebSocket } from '@/hooks/useWebSocket';

export default function DashboardPage() {
  const [stats,     setStats]     = useState<DashboardStats>(mockData.stats());
  const [approvals, setApprovals] = useState<ApprovalItem[]>(mockData.approvals());
  const [activity,  setActivity]  = useState<ActivityEvent[]>(mockData.activity());
  const [tasks,     setTasks]     = useState<TaskFile[]>(mockData.tasks());
  const [bots,      setBots]      = useState<BotStatus[]>(mockData.bots());
  const [loading,   setLoading]   = useState(false);

  // Try fetching real data (fallback to mock on error)
  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [s, a, act, t, b] = await Promise.all([
        api.fetchDashboard().catch(() => mockData.stats()),
        api.fetchApprovals().catch(() => mockData.approvals()),
        api.fetchActivity().catch(() => mockData.activity()),
        api.fetchTasks().catch(() => mockData.tasks()),
        api.fetchBots().catch(() => mockData.bots()),
      ]);
      setStats(s); setApprovals(a); setActivity(act); setTasks(t); setBots(b);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // WebSocket live updates
  const { connected } = useWebSocket(useCallback((ev) => {
    if (ev.type === 'stats_update')       setStats(prev => ({ ...prev, ...(ev.data as Partial<DashboardStats>) }));
    if (ev.type === 'new_approval')       setApprovals(prev => [ev.data as unknown as ApprovalItem, ...prev]);
    if (ev.type === 'new_activity')       setActivity(prev => [ev.data as unknown as ActivityEvent, ...prev.slice(0, 49)]);
    if (ev.type === 'bot_status_change')  setBots(prev => prev.map(b => b.name === (ev.data as unknown as BotStatus).name ? { ...b, ...ev.data } : b));
  }, []));

  async function handleApprove(id: string) {
    await api.approveItem(id).catch(() => {});
    setApprovals(prev => prev.filter(a => a.id !== id));
    setStats(prev => ({ ...prev, approvalsCount: Math.max(0, prev.approvalsCount - 1) }));
  }
  async function handleReject(id: string) {
    await api.rejectItem(id).catch(() => {});
    setApprovals(prev => prev.filter(a => a.id !== id));
    setStats(prev => ({ ...prev, approvalsCount: Math.max(0, prev.approvalsCount - 1) }));
  }
  async function handleBotToggle(name: string) {
    const result = await api.toggleBot(name).catch(() => null);
    if (result) {
      setBots(prev => prev.map(b => b.name === name ? { ...b, status: result.status as BotStatus['status'] } : b));
    }
  }

  return (
    <div className="space-y-5 max-w-[1400px] mx-auto">
      {/* Live indicator */}
      <div className="flex items-center justify-between">
        <div />
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-500 dot-pulse' : 'bg-gray-600'}`} />
          <span className="text-xs" style={{ color: '#374151' }}>
            {connected ? 'Live' : 'Offline mode'}
          </span>
        </div>
      </div>

      {/* Hero */}
      <HeroCard stats={stats} />

      {/* Metrics */}
      <MetricCards stats={stats} />

      {/* Two-column: Approvals + Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <ApprovalsPanel items={approvals} onApprove={handleApprove} onReject={handleReject} />
        <ActivityPanel  events={activity} />
      </div>

      {/* Tasks */}
      <TasksGrid tasks={tasks} />

      {/* Bots */}
      <BotsGrid bots={bots} onToggle={handleBotToggle} />
    </div>
  );
}
