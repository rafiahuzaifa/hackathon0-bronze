import { NextRequest, NextResponse } from 'next/server';

async function callClaude(prompt: string): Promise<string> {
  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) return '[No ANTHROPIC_API_KEY set — add it in Vercel environment variables]';

  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'x-api-key': key,
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      model: 'claude-haiku-4-5-20251001',
      max_tokens: 512,
      messages: [{ role: 'user', content: prompt }],
    }),
  });
  const data = await res.json() as { content: Array<{ text: string }> };
  return data.content?.[0]?.text || '';
}

export async function POST(req: NextRequest) {
  const body = await req.json() as { content: string; platforms?: string[]; image_url?: string; schedule_time?: string };
  const { content, platforms = ['linkedin', 'twitter'], schedule_time } = body;
  const live = process.env.AI_LIVE_MODE === 'true';

  // Generate optimized versions per platform
  const platformResults: Record<string, unknown> = {};

  for (const platform of platforms) {
    const prompt = `You are an AI social media manager. Optimize this post for ${platform}:

"${content}"

Return ONLY the optimized post text, no explanations. Keep it authentic and engaging.
${platform === 'twitter' ? 'Max 280 characters.' : ''}`;

    const optimized = await callClaude(prompt);

    if (live && platform === 'linkedin' && process.env.LINKEDIN_ACCESS_TOKEN) {
      // Real LinkedIn post (simplified)
      try {
        const profileRes = await fetch('https://api.linkedin.com/v2/userinfo', {
          headers: { Authorization: `Bearer ${process.env.LINKEDIN_ACCESS_TOKEN}` },
        });
        const profile = await profileRes.json() as { sub: string };
        await fetch('https://api.linkedin.com/v2/ugcPosts', {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${process.env.LINKEDIN_ACCESS_TOKEN}`,
            'Content-Type': 'application/json',
            'X-Restli-Protocol-Version': '2.0.0',
          },
          body: JSON.stringify({
            author: `urn:li:person:${profile.sub}`,
            lifecycleState: 'PUBLISHED',
            specificContent: { 'com.linkedin.ugc.ShareContent': { shareCommentary: { text: optimized }, shareMediaCategory: 'NONE' } },
            visibility: { 'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC' },
          }),
        });
        platformResults[platform] = { status: 'posted', text: optimized };
      } catch {
        platformResults[platform] = { status: 'error', text: optimized, error: 'LinkedIn post failed' };
      }
    } else if (live && platform === 'twitter' && process.env.TWITTER_BEARER_TOKEN) {
      platformResults[platform] = { status: 'queued_live', text: optimized, note: 'Twitter OAuth2 required for posting' };
    } else {
      platformResults[platform] = {
        status: schedule_time ? 'scheduled' : 'queued_approval',
        text: optimized,
        scheduledFor: schedule_time || null,
        mode: live ? 'live' : 'demo',
      };
    }
  }

  return NextResponse.json({
    status: 'ok',
    mode: live ? 'live' : 'demo',
    platforms: platformResults,
    originalContent: content,
    timestamp: new Date().toISOString(),
  });
}
