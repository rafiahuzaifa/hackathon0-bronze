import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json([
    { id: 't1', filename: 'EMAIL_20260313_092341.md', type: 'EMAIL',      status: 'done',         createdAt: new Date(Date.now() - 2 * 86400000).toISOString() },
    { id: 't2', filename: 'WHATSAPP_ali_20260313.md', type: 'WHATSAPP',   status: 'needs_review', createdAt: new Date(Date.now() - 2 * 86400000).toISOString() },
    { id: 't3', filename: 'EMAIL_20260312_174502.md', type: 'EMAIL',      status: 'done',         createdAt: new Date(Date.now() - 3 * 86400000).toISOString() },
    { id: 't4', filename: 'EMAIL_20260312_110023.md', type: 'EMAIL',      status: 'done',         createdAt: new Date(Date.now() - 3 * 86400000).toISOString() },
    { id: 't5', filename: 'BANK_ALERT_20260311.md',   type: 'BANK_ALERT', status: 'done',         createdAt: new Date(Date.now() - 4 * 86400000).toISOString() },
  ]);
}
