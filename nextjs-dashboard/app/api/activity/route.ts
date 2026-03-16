import { NextResponse } from 'next/server';

export async function GET() {
  const now = Date.now();
  return NextResponse.json([
    { id: 'e1', timestamp: new Date(now - 2 * 60000).toISOString(),   type: 'email',    message: 'Email from support@stripe.com → intent: invoice → auto-replied ✓',          status: 'ok' },
    { id: 'e2', timestamp: new Date(now - 5 * 60000).toISOString(),   type: 'linkedin', message: 'LinkedIn post queued for approval (risk: medium)',                          status: 'ok' },
    { id: 'e3', timestamp: new Date(now - 10 * 60000).toISOString(),  type: 'whatsapp', message: 'WhatsApp message from Ali Hassan → partnership intent detected',            status: 'ok' },
    { id: 'e4', timestamp: new Date(now - 15 * 60000).toISOString(),  type: 'email',    message: 'Email reply to ahmed@example.com flagged as high-risk — pending approval', status: 'warning' },
    { id: 'e5', timestamp: new Date(now - 50 * 60000).toISOString(),  type: 'bank',     message: 'Bank CSV uploaded: transactions_mar2026.csv (238 rows processed)',           status: 'ok' },
    { id: 'e6', timestamp: new Date(now - 90 * 60000).toISOString(),  type: 'vault',    message: 'Vault RAG reindex completed — 312 documents indexed',                      status: 'ok' },
    { id: 'e7', timestamp: new Date(now - 110 * 60000).toISOString(), type: 'bank',     message: 'Bank anomaly detected: ROUND_AMOUNT_FLAG on 3 transactions',                status: 'warning' },
    { id: 'e8', timestamp: new Date(now - 180 * 60000).toISOString(), type: 'system',   message: 'Weekly CEO Briefing generated and delivered',                              status: 'ok' },
  ]);
}
