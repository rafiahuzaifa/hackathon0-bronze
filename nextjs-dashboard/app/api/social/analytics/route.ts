import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json([
    { platform: 'linkedin', followers: 2847, posts_this_week: 3, impressions: 12400, engagement_rate: 4.2, top_post: 'AI Employee announcement — 847 impressions' },
    { platform: 'twitter',  followers: 1203, posts_this_week: 7, impressions: 8900,  engagement_rate: 3.1, top_post: 'Hackathon thread — 312 likes' },
    { platform: 'facebook', followers: 983,  posts_this_week: 2, impressions: 4200,  engagement_rate: 2.8, top_post: 'Product demo video — 198 reactions' },
    { platform: 'instagram',followers: 1580, posts_this_week: 4, impressions: 6700,  engagement_rate: 5.7, top_post: 'Behind the scenes — 89 saves' },
  ]);
}
