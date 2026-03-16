import { NextResponse } from 'next/server';

export async function GET() {
  const live = process.env.AI_LIVE_MODE === 'true';
  return NextResponse.json({
    botsOnline: 9,
    botsTotal: 11,
    tasksDone: 47,
    inboxCount: 3,
    approvalsCount: 3,
    monthlyIncome: 8500,
    monthlyExpenses: 3200,
    currency: 'PKR',
    lastUpdated: new Date().toISOString(),
    dryRun: !live,
  });
}
