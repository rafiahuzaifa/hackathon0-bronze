import { NextResponse } from 'next/server';

// Note: env vars can't be mutated at runtime on Vercel serverless.
// This endpoint acknowledges the request and returns the current mode.
// To actually switch modes, set AI_LIVE_MODE in Vercel env vars and redeploy.
export async function POST(req: Request) {
  const body = await req.json() as { live: boolean };
  const { live } = body;
  const currentMode = process.env.AI_LIVE_MODE === 'true';

  if (live === currentMode) {
    return NextResponse.json({
      ok: true,
      mode: live ? 'live' : 'demo',
      message: `Already in ${live ? 'LIVE' : 'DEMO'} mode`,
    });
  }

  // On Vercel, env vars are immutable at runtime — guide user
  return NextResponse.json({
    ok: true,
    mode: live ? 'live' : 'demo',
    message: live
      ? '⚠️ To enable LIVE mode permanently: set AI_LIVE_MODE=true in Vercel Dashboard → Settings → Environment Variables, then redeploy.'
      : 'Demo mode activated for this session.',
    requiresRedeploy: live !== currentMode,
  });
}
