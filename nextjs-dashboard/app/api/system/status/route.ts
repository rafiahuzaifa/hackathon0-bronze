import { NextResponse } from 'next/server';

export async function GET() {
  const live = process.env.AI_LIVE_MODE === 'true';

  const platforms = [
    { id: 'claude',     name: 'Claude AI',    connected: !!process.env.ANTHROPIC_API_KEY },
    { id: 'gmail',      name: 'Gmail',        connected: !!process.env.GMAIL_CREDENTIALS },
    { id: 'linkedin',   name: 'LinkedIn',     connected: !!process.env.LINKEDIN_ACCESS_TOKEN },
    { id: 'twitter',    name: 'Twitter/X',    connected: !!process.env.TWITTER_BEARER_TOKEN },
    { id: 'facebook',   name: 'Facebook',     connected: !!process.env.FACEBOOK_PAGE_ACCESS_TOKEN },
    { id: 'instagram',  name: 'Instagram',    connected: !!process.env.INSTAGRAM_ACCESS_TOKEN },
    { id: 'whatsapp',   name: 'WhatsApp',     connected: false },
    { id: 'bank',       name: 'Bank Monitor', connected: true },
  ];

  return NextResponse.json({
    mode: live ? 'live' : 'demo',
    version: '1.0.0',
    uptime: '4h 23m',
    platforms,
    botsRunning: 9,
    botsTotal: 11,
    tasksToday: 47,
    timestamp: new Date().toISOString(),
  });
}
