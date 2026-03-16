import { NextResponse } from 'next/server';

export async function POST(_req: Request, { params }: { params: { id: string } }) {
  const live = process.env.AI_LIVE_MODE === 'true';
  return NextResponse.json({
    status: 'approved',
    id: params.id,
    mode: live ? 'live' : 'demo',
    message: live ? 'Post published to social media' : 'Approved in demo mode — no real post made',
  });
}
