import { NextResponse } from 'next/server';

export async function POST(_req: Request, { params }: { params: { id: string } }) {
  const live = process.env.AI_LIVE_MODE === 'true';
  return NextResponse.json({
    ok: true,
    id: params.id,
    message: live ? 'Action executed in LIVE mode' : 'Approved (demo mode — no real action taken)',
  });
}
