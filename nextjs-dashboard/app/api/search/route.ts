import { NextRequest, NextResponse } from 'next/server';

const VAULT_DOCS = [
  { id: 'd1', title: 'LinkedIn Post — Q1 Growth', type: 'social_post',  content: 'AI Employee achieved 34% growth in Q1 2026. Key metrics: 47 tasks automated, 9 bots running, email response time reduced by 80%.' },
  { id: 'd2', title: 'Bank Alert — March 2026',   type: 'bank_alert',   content: 'ROUND_AMOUNT_FLAG detected on 3 transactions: PKR 5000.00, PKR 10000.00, PKR 2500.00. Vendor: UNKNOWN_VENDOR. Requires review.' },
  { id: 'd3', title: 'Email — Partnership TechCorp', type: 'email',     content: 'TechCorp Ltd reached out requesting a 3-month pilot of AI Employee. Proposal: PKR 150,000/month retainer. Risk: high. Pending approval.' },
  { id: 'd4', title: 'Weekly CEO Briefing',        type: 'briefing',    content: 'Week of March 10-17 2026. Tasks completed: 47. Escalations: 2 (email, bank). Social: 3 LinkedIn posts, 7 tweets. Finance: PKR 8500 income, PKR 3200 expenses.' },
  { id: 'd5', title: 'Webhook — Stripe Payment',   type: 'webhook',     content: 'Stripe payment received: PKR 25,000 from client@example.com. Invoice #INV-2026-034. Auto-logged to finance.' },
  { id: 'd6', title: 'WhatsApp — Ali Hassan',      type: 'whatsapp',    content: 'Ali Hassan sent: "Interested in partnering on the AI project. Can we schedule a call?" Intent: partnership. Claude draft reply ready for approval.' },
  { id: 'd7', title: 'Bot Status — System Health', type: 'system',      content: 'All 9 active bots running healthy. Gmail Bot: 0 new emails. WhatsApp Bot: 0 unread. Bank Monitor: last CSV 1 hour ago. Vault Sync: 312 docs indexed.' },
];

export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get('q') || '';

  if (!q.trim()) {
    return NextResponse.json({ results: [], query: '' });
  }

  const key = process.env.ANTHROPIC_API_KEY;
  let results: unknown[] = [];

  if (key) {
    // Use Claude to find relevant docs
    try {
      const docsContext = VAULT_DOCS.map(d => `[${d.id}] ${d.title} (${d.type}): ${d.content}`).join('\n\n');

      const prompt = `You are an AI vault search engine. A user searched for: "${q}"

Here are the vault documents:
${docsContext}

Return a JSON array of the most relevant document IDs with relevance scores (0-1) and a brief reason.
Format: [{"id": "d1", "score": 0.95, "reason": "..."}, ...]
Return only valid JSON, no explanation.`;

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
      const text = data.content?.[0]?.text || '[]';
      const matches = JSON.parse(text) as Array<{ id: string; score: number; reason: string }>;

      results = matches
        .sort((a, b) => b.score - a.score)
        .slice(0, 5)
        .map(m => {
          const doc = VAULT_DOCS.find(d => d.id === m.id);
          return doc ? { ...doc, score: m.score, reason: m.reason } : null;
        })
        .filter(Boolean);
    } catch {
      // Fallback to keyword search
      results = keywordSearch(q);
    }
  } else {
    // No API key — keyword search fallback
    results = keywordSearch(q);
  }

  return NextResponse.json({ results, query: q, powered_by: key ? 'claude-ai' : 'keyword-search' });
}

function keywordSearch(q: string) {
  const lower = q.toLowerCase();
  return VAULT_DOCS
    .filter(d => d.title.toLowerCase().includes(lower) || d.content.toLowerCase().includes(lower))
    .slice(0, 5)
    .map(d => ({ ...d, score: 0.7, reason: 'Keyword match' }));
}
