import { NextResponse } from 'next/server';

export async function GET() {
  const now = Date.now();
  return NextResponse.json([
    { id: 'f1', platform: 'linkedin', content: 'Excited to share our AI Employee project for the Panaversity Hackathon 2026! 🚀 This system acts as a full personal AI employee — handling emails, social media, bank monitoring, and more. Built with Claude AI + Next.js + FastAPI. #AIEmployee #Panaversity', status: 'approved', postedAt: new Date(now - 2 * 3600000).toISOString(), likes: 47, comments: 8 },
    { id: 'f2', platform: 'twitter',  content: 'Just deployed the AI Employee dashboard live! It now manages emails, WhatsApp, LinkedIn, Twitter, and bank transactions autonomously. Demo: nextjs-dashboard-xi-one-64.vercel.app #AI #Hackathon', status: 'approved', postedAt: new Date(now - 5 * 3600000).toISOString(), likes: 23, comments: 3 },
    { id: 'f3', platform: 'linkedin', content: 'Key feature of AI Employee: the APPROVAL VAULT. Every risky action (sending emails, posting, bank ops) goes through a human-in-the-loop approval flow before execution. Safety first! 🛡️', status: 'pending', createdAt: new Date(now - 30 * 60000).toISOString() },
    { id: 'f4', platform: 'instagram',content: 'Dashboard screenshot of the AI Employee control center. Dark theme, real-time bot monitoring, and one-click approval flows. ✨', status: 'approved', postedAt: new Date(now - 24 * 3600000).toISOString(), likes: 89, comments: 12 },
  ]);
}
