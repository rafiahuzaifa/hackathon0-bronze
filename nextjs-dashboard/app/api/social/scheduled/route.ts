import { NextResponse } from 'next/server';

export async function GET() {
  const now = Date.now();
  return NextResponse.json([
    { id: 's1', filename: 'SCHEDULED_linkedin_20260318_090000.md', platform: 'linkedin', content: 'Weekly AI insights post scheduled for Monday morning', scheduledFor: new Date(now + 18 * 3600000).toISOString() },
    { id: 's2', filename: 'SCHEDULED_twitter_20260318_120000.md',  platform: 'twitter',  content: 'Noon tweet about the hackathon results', scheduledFor: new Date(now + 21 * 3600000).toISOString() },
  ]);
}

export async function DELETE(_req: Request, { params }: { params: { filename: string } }) {
  return NextResponse.json({ status: 'cancelled', filename: params?.filename });
}
