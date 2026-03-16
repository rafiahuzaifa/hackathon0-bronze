// api.ts — API client for AI Employee backend
import type { DashboardStats, ApprovalItem, ActivityEvent, BotStatus, TaskFile, FinanceData } from './types';

// Empty string = same-origin Next.js API routes (works on Vercel without separate backend)
const BASE = process.env.NEXT_PUBLIC_API_URL || '';

async function apiFetch<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  fetchDashboard: () => apiFetch<DashboardStats>('/api/dashboard'),
  fetchApprovals: () => apiFetch<ApprovalItem[]>('/api/approvals'),
  approveItem:    (id: string) => apiFetch<{ ok: boolean }>(`/api/approvals/${id}/approve`, { method: 'POST' }),
  rejectItem:     (id: string) => apiFetch<{ ok: boolean }>(`/api/approvals/${id}/reject`,  { method: 'POST' }),
  fetchActivity:  (n = 50) => apiFetch<ActivityEvent[]>(`/api/activity?n=${n}`),
  fetchBots:      () => apiFetch<BotStatus[]>('/api/bots'),
  toggleBot:      (name: string) => apiFetch<{ ok: boolean; status: string }>(`/api/bots/${name}/toggle`, { method: 'POST' }),
  fetchTasks:     () => apiFetch<TaskFile[]>('/api/tasks'),
  fetchFinance:   () => apiFetch<FinanceData>('/api/finance'),

  // Social media
  socialPost:       (body: { content: string; platforms?: string[]; image_url?: string; schedule_time?: string }) =>
                      apiFetch<{ status: string; result: unknown }>('/api/social/post', { method: 'POST', body: JSON.stringify(body) }),
  fetchScheduled:   () => apiFetch<unknown[]>('/api/social/scheduled'),
  cancelScheduled:  (filename: string) => apiFetch<{ status: string }>(`/api/social/scheduled/${encodeURIComponent(filename)}`, { method: 'DELETE' }),
  fetchAnalytics:   () => apiFetch<unknown[]>('/api/social/analytics'),
  fetchSocialFeed:  () => apiFetch<unknown[]>('/api/social/feed'),
  approveSocial:    (id: string) => apiFetch<{ status: string }>(`/api/social/approve/${id}`, { method: 'POST' }),
};

// ---- Mock data (used when API is not available) ----
export const mockData = {
  stats: (): DashboardStats => ({
    botsOnline: 9, botsTotal: 11, tasksDone: 47,
    inboxCount: 3, approvalsCount: 3,
    monthlyIncome: 8500, monthlyExpenses: 3200, currency: 'PKR',
    lastUpdated: new Date().toISOString(), dryRun: true,
  }),

  approvals: (): ApprovalItem[] => [
    { id: 'a1', filename: 'post_linkedin_q1.md', type: 'post_linkedin', description: 'LinkedIn post about Q1 results and growth metrics', risk: 'medium', createdAt: new Date(Date.now() - 86400000).toISOString() },
    { id: 'a2', filename: 'email_partnership.md', type: 'send_email',   description: 'Reply to partnership proposal from TechCorp Ltd', risk: 'high',   createdAt: new Date(Date.now() - 86400000).toISOString() },
    { id: 'a3', filename: 'tweet_launch.md',      type: 'post_twitter',  description: 'Tweet about AI Employee launch and hackathon', risk: 'medium', createdAt: new Date(Date.now() - 172800000).toISOString() },
  ],

  activity: (): ActivityEvent[] => [
    { id: 'e1', timestamp: new Date(Date.now() - 2 * 60000).toISOString(),   type: 'email',    message: 'Email from support@stripe.com → intent: invoice → auto-replied ✓',           status: 'ok' },
    { id: 'e2', timestamp: new Date(Date.now() - 5 * 60000).toISOString(),   type: 'linkedin', message: 'LinkedIn post queued for approval (risk: medium)',                           status: 'ok' },
    { id: 'e3', timestamp: new Date(Date.now() - 10 * 60000).toISOString(),  type: 'whatsapp', message: 'WhatsApp message from Ali Hassan → partnership intent detected',             status: 'ok' },
    { id: 'e4', timestamp: new Date(Date.now() - 15 * 60000).toISOString(),  type: 'email',    message: 'Email reply to ahmed@example.com flagged as high-risk — pending approval',  status: 'warning' },
    { id: 'e5', timestamp: new Date(Date.now() - 50 * 60000).toISOString(),  type: 'bank',     message: 'Bank CSV uploaded: transactions_mar2026.csv (238 rows processed)',            status: 'ok' },
    { id: 'e6', timestamp: new Date(Date.now() - 90 * 60000).toISOString(),  type: 'vault',    message: 'Vault RAG reindex completed — 312 documents indexed',                       status: 'ok' },
    { id: 'e7', timestamp: new Date(Date.now() - 110 * 60000).toISOString(), type: 'bank',     message: 'Bank anomaly detected: ROUND_AMOUNT_FLAG on 3 transactions',                 status: 'warning' },
    { id: 'e8', timestamp: new Date(Date.now() - 180 * 60000).toISOString(), type: 'system',   message: 'Weekly CEO Briefing generated and delivered',                               status: 'ok' },
  ],

  bots: (): BotStatus[] => [
    { name: 'main_brain',    displayName: 'Main Brain',     emoji: '🧠', status: 'running', uptime: '4h 23m', lastAction: 'Processed EMAIL_20260315',   description: 'Core AI orchestrator' },
    { name: 'file_watcher',  displayName: 'File Watcher',   emoji: '👁',  status: 'running', uptime: '4h 23m', lastAction: 'New file detected',           description: 'Monitors vault/Needs_Action' },
    { name: 'gmail_bot',     displayName: 'Gmail Bot',      emoji: '📧', status: 'running', uptime: '4h 20m', lastAction: '4 min ago — 0 new emails',    description: 'Gmail IMAP watcher' },
    { name: 'gmail_push',    displayName: 'Gmail Push',     emoji: '📨', status: 'running', uptime: '4h 20m', lastAction: 'Push subscription active',    description: 'Gmail Pub/Sub push' },
    { name: 'bank_monitor',  displayName: 'Bank Monitor',   emoji: '🏦', status: 'running', uptime: '4h 18m', lastAction: '1 hour ago — CSV processed',  description: 'Bank transaction monitor' },
    { name: 'webhook_server',displayName: 'Webhook Server', emoji: '🔗', status: 'running', uptime: '4h 23m', lastAction: 'Listening on :8001',           description: 'Incoming webhook handler' },
    { name: 'whatsapp_bot',  displayName: 'WhatsApp Bot',   emoji: '💬', status: 'running', uptime: '4h 15m', lastAction: '2 min ago — 0 new msgs',      description: 'WhatsApp Playwright bot' },
    { name: 'ai_memory',     displayName: 'AI Memory',      emoji: '🧩', status: 'stopped', lastAction: 'Stopped manually',                              description: 'RAG + vector memory' },
    { name: 'ceo_briefing',  displayName: 'CEO Briefing',   emoji: '📋', status: 'stopped', lastAction: 'Next: Sunday 22:00',                            description: 'Weekly briefing generator' },
    { name: 'vault_sync',    displayName: 'Vault Sync',     emoji: '🗄',  status: 'running', uptime: '4h 23m', lastAction: '312 docs indexed',            description: 'Obsidian vault sync' },
    { name: 'health_watch',  displayName: 'Health Watch',   emoji: '❤️', status: 'running', uptime: '4h 23m', lastAction: 'All systems green',           description: 'System health monitor' },
  ],

  tasks: (): TaskFile[] => [
    { id: 't1', filename: 'EMAIL_20260313_092341.md', type: 'EMAIL',      status: 'done',        createdAt: new Date(Date.now() - 2 * 86400000).toISOString() },
    { id: 't2', filename: 'WHATSAPP_ali_20260313.md', type: 'WHATSAPP',   status: 'needs_review',createdAt: new Date(Date.now() - 2 * 86400000).toISOString() },
    { id: 't3', filename: 'EMAIL_20260312_174502.md', type: 'EMAIL',      status: 'done',        createdAt: new Date(Date.now() - 3 * 86400000).toISOString() },
    { id: 't4', filename: 'EMAIL_20260312_110023.md', type: 'EMAIL',      status: 'done',        createdAt: new Date(Date.now() - 3 * 86400000).toISOString() },
    { id: 't5', filename: 'BANK_ALERT_20260311.md',   type: 'BANK_ALERT', status: 'done',        createdAt: new Date(Date.now() - 4 * 86400000).toISOString() },
  ],

  finance: (): FinanceData => ({
    month: 'March 2026', income: 8500, expenses: 3200, net: 5300,
    currency: 'PKR', incomeChangePercent: 34,
    incomeBreakdown: [
      { label: 'Client Retainers', amount: 5000 },
      { label: 'Project Work',     amount: 2500 },
      { label: 'Consulting',       amount: 1000 },
    ],
    expensesBreakdown: [
      { label: 'SaaS Tools', amount: 800 },
      { label: 'API Credits', amount: 600 },
      { label: 'Contractors', amount: 1800 },
    ],
  }),
};
