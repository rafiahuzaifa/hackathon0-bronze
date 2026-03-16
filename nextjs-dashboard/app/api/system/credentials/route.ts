import { NextResponse } from 'next/server';

export async function GET() {
  // Return which credentials are configured (never expose values)
  return NextResponse.json({
    claude:     { configured: !!process.env.ANTHROPIC_API_KEY },
    gmail:      { configured: !!process.env.GMAIL_CREDENTIALS },
    linkedin:   { configured: !!process.env.LINKEDIN_ACCESS_TOKEN },
    twitter:    { configured: !!process.env.TWITTER_BEARER_TOKEN },
    facebook:   { configured: !!process.env.FACEBOOK_PAGE_ACCESS_TOKEN },
    instagram:  { configured: !!process.env.INSTAGRAM_ACCESS_TOKEN },
    whatsapp:   { configured: false },
    bank:       { configured: true },
  });
}

export async function POST(req: Request) {
  // On Vercel, credentials must be set as env vars in the dashboard.
  // This endpoint guides the user.
  const body = await req.json() as { platform: string; credentials: Record<string, string> };
  return NextResponse.json({
    ok: false,
    platform: body.platform,
    message: 'On Vercel, set credentials as Environment Variables in the Vercel Dashboard (Settings → Environment Variables), then redeploy. Never send API keys through this form in production.',
    vercelDashboard: 'https://vercel.com/dashboard',
  });
}
