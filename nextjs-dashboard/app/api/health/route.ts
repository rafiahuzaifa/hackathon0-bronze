import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({
    status: 'ok',
    version: '1.0.0',
    mode: process.env.AI_LIVE_MODE === 'true' ? 'live' : 'demo',
    timestamp: new Date().toISOString(),
  });
}
