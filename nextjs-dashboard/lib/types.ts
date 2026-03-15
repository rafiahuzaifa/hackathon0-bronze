// types.ts — Shared TypeScript interfaces for AI Employee Dashboard

export type BotStatusType = 'running' | 'stopped' | 'error' | 'starting';
export type RiskLevel = 'low' | 'medium' | 'high';
export type TaskStatus = 'done' | 'needs_review' | 'pending' | 'in_progress';
export type ApprovalType = 'post_linkedin' | 'post_twitter' | 'post_facebook' | 'post_instagram' | 'send_email' | 'send_whatsapp' | 'payment';

export interface BotStatus {
  name: string;
  displayName: string;
  emoji: string;
  status: BotStatusType;
  pid?: number;
  uptime?: string;
  lastAction?: string;
  lastActionAt?: string;
  description: string;
}

export interface ApprovalItem {
  id: string;
  filename: string;
  type: ApprovalType;
  description: string;
  fullContent?: string;
  risk: RiskLevel;
  createdAt: string;
  expiresAt?: string;
  metadata?: Record<string, string>;
}

export interface ActivityEvent {
  id: string;
  timestamp: string;
  type: 'email' | 'whatsapp' | 'linkedin' | 'twitter' | 'bank' | 'vault' | 'system' | 'alert';
  message: string;
  status: 'ok' | 'warning' | 'error';
  details?: string;
}

export interface TaskFile {
  id: string;
  filename: string;
  type: 'EMAIL' | 'WHATSAPP' | 'BANK_ALERT' | 'LINKEDIN' | 'TWITTER' | 'MANUAL';
  status: TaskStatus;
  createdAt: string;
  processedAt?: string;
}

export interface FinanceData {
  month: string;
  income: number;
  expenses: number;
  net: number;
  currency: string;
  incomeChangePercent: number;
  expensesBreakdown: { label: string; amount: number }[];
  incomeBreakdown: { label: string; amount: number }[];
}

export interface DashboardStats {
  botsOnline: number;
  botsTotal: number;
  tasksDone: number;
  inboxCount: number;
  approvalsCount: number;
  monthlyIncome: number;
  monthlyExpenses: number;
  currency: string;
  lastUpdated: string;
  dryRun: boolean;
}

export interface ChartDataPoint {
  name: string;
  value: number;
}
