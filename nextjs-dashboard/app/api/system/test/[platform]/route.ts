import { NextResponse } from 'next/server';

async function testClaude(): Promise<{ ok: boolean; message: string }> {
  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) return { ok: false, message: 'ANTHROPIC_API_KEY not set' };
  try {
    const res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'x-api-key': key,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        model: 'claude-haiku-4-5-20251001',
        max_tokens: 10,
        messages: [{ role: 'user', content: 'Say "ok"' }],
      }),
    });
    if (res.ok) return { ok: true, message: 'Claude API connected ✓' };
    return { ok: false, message: `Claude API error: ${res.status}` };
  } catch (e) {
    return { ok: false, message: `Connection failed: ${String(e)}` };
  }
}

async function testLinkedIn(): Promise<{ ok: boolean; message: string }> {
  const token = process.env.LINKEDIN_ACCESS_TOKEN;
  if (!token) return { ok: false, message: 'LINKEDIN_ACCESS_TOKEN not set' };
  try {
    const res = await fetch('https://api.linkedin.com/v2/userinfo', {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) return { ok: true, message: 'LinkedIn connected ✓' };
    return { ok: false, message: `LinkedIn error: ${res.status}` };
  } catch (e) {
    return { ok: false, message: `Connection failed: ${String(e)}` };
  }
}

async function testTwitter(): Promise<{ ok: boolean; message: string }> {
  const token = process.env.TWITTER_BEARER_TOKEN;
  if (!token) return { ok: false, message: 'TWITTER_BEARER_TOKEN not set' };
  try {
    const res = await fetch('https://api.twitter.com/2/users/me', {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) return { ok: true, message: 'Twitter connected ✓' };
    return { ok: false, message: `Twitter error: ${res.status}` };
  } catch (e) {
    return { ok: false, message: `Connection failed: ${String(e)}` };
  }
}

export async function POST(_req: Request, { params }: { params: { platform: string } }) {
  const { platform } = params;
  let result: { ok: boolean; message: string };

  switch (platform) {
    case 'claude':
      result = await testClaude();
      break;
    case 'linkedin':
      result = await testLinkedIn();
      break;
    case 'twitter':
      result = await testTwitter();
      break;
    case 'bank':
      result = { ok: true, message: 'Bank monitor ready (CSV upload mode) ✓' };
      break;
    default:
      result = { ok: false, message: `${platform}: add your API key in Vercel env vars to test` };
  }

  return NextResponse.json({ platform, ...result });
}
