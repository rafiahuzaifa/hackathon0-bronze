import { NextResponse } from 'next/server';

const APPROVALS = [
  { id: 'a1', filename: 'post_linkedin_q1.md', type: 'post_linkedin', description: 'LinkedIn post about Q1 results and growth metrics for AI Employee project', risk: 'medium', createdAt: new Date(Date.now() - 86400000).toISOString() },
  { id: 'a2', filename: 'email_partnership.md', type: 'send_email', description: 'Reply to partnership proposal from TechCorp Ltd — requesting 3-month pilot', risk: 'high', createdAt: new Date(Date.now() - 86400000).toISOString() },
  { id: 'a3', filename: 'tweet_launch.md', type: 'post_twitter', description: 'Tweet about AI Employee launch and Panaversity hackathon submission', risk: 'medium', createdAt: new Date(Date.now() - 172800000).toISOString() },
];

export async function GET() {
  return NextResponse.json(APPROVALS);
}
