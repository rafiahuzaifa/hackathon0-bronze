import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json([
    { name: 'main_brain',     displayName: 'Main Brain',     emoji: '🧠', status: 'running', uptime: '4h 23m', lastAction: 'Processed EMAIL_20260315',    description: 'Core AI orchestrator' },
    { name: 'file_watcher',   displayName: 'File Watcher',   emoji: '👁',  status: 'running', uptime: '4h 23m', lastAction: 'New file detected',            description: 'Monitors vault/Needs_Action' },
    { name: 'gmail_bot',      displayName: 'Gmail Bot',      emoji: '📧', status: 'running', uptime: '4h 20m', lastAction: '4 min ago — 0 new emails',     description: 'Gmail IMAP watcher' },
    { name: 'gmail_push',     displayName: 'Gmail Push',     emoji: '📨', status: 'running', uptime: '4h 20m', lastAction: 'Push subscription active',     description: 'Gmail Pub/Sub push' },
    { name: 'bank_monitor',   displayName: 'Bank Monitor',   emoji: '🏦', status: 'running', uptime: '4h 18m', lastAction: '1 hour ago — CSV processed',   description: 'Bank transaction monitor' },
    { name: 'webhook_server', displayName: 'Webhook Server', emoji: '🔗', status: 'running', uptime: '4h 23m', lastAction: 'Listening on :8001',            description: 'Incoming webhook handler' },
    { name: 'whatsapp_bot',   displayName: 'WhatsApp Bot',   emoji: '💬', status: 'running', uptime: '4h 15m', lastAction: '2 min ago — 0 new msgs',       description: 'WhatsApp Playwright bot' },
    { name: 'ai_memory',      displayName: 'AI Memory',      emoji: '🧩', status: 'stopped', lastAction: 'Stopped manually',                               description: 'RAG + vector memory' },
    { name: 'ceo_briefing',   displayName: 'CEO Briefing',   emoji: '📋', status: 'stopped', lastAction: 'Next: Sunday 22:00',                             description: 'Weekly briefing generator' },
    { name: 'vault_sync',     displayName: 'Vault Sync',     emoji: '🗄',  status: 'running', uptime: '4h 23m', lastAction: '312 docs indexed',             description: 'Obsidian vault sync' },
    { name: 'health_watch',   displayName: 'Health Watch',   emoji: '❤️', status: 'running', uptime: '4h 23m', lastAction: 'All systems green',            description: 'System health monitor' },
  ]);
}
