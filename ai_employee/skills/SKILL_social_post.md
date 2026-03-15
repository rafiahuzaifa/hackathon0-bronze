---
skill: social_post
version: 1.0
triggers:
  - manual trigger from dashboard
  - weekly schedule (Mon/Wed/Fri 10:00 AM)
  - milestone event (task_done, briefing_generated)
input: topic string OR Needs_Action/SOCIAL_*.md file
output: platform-specific drafts in Pending_Approval/ (ALWAYS requires human approval)
approval_required: true
dry_run_safe: true
---

# SKILL: Social Media Post Drafter

## Goal
Draft platform-optimised posts from a topic or event, assess risk, stage for human approval. Never post directly.

## Platform Specs

| Platform  | Char Limit | Tone          | Best Time    | Frequency   |
|-----------|-----------|---------------|--------------|-------------|
| LinkedIn  | 3,000     | Professional  | Tue 9–11 AM  | 3×/week     |
| Twitter/X | 280       | Conversational| Mon–Fri 9 AM | 1–2×/day    |
| Facebook  | 63,206    | Friendly      | Wed 1–3 PM   | 1×/day      |
| Instagram | 2,200     | Visual/Casual | Fri 11 AM    | 1×/day      |

## Steps

1. **Read input** — topic string or parse SOCIAL_*.md metadata
2. **Identify platforms** — default: LinkedIn + Twitter. Add others if specified.
3. **Draft per platform**:
   - LinkedIn: 150–300 words, professional insight, 3–5 relevant hashtags, call-to-action
   - Twitter: ≤280 chars, punchy, 1–2 hashtags, optional thread indicator (1/3)
   - Facebook: 100–200 words, friendly, link preview friendly, question at end
   - Instagram: 150–200 words, emoji-friendly, 10–15 hashtags in first comment
4. **Risk assessment** (see rules below) → set `risk: low|medium|high`
5. **Write drafts** to `vault/Pending_Approval/SOCIAL_{platform}_{timestamp}.md`
6. **Set** `approval_required: true` on ALL social posts without exception
7. **Log** draft event

## Content Pillars (from Business_Goals.md)
1. AI & Automation insights
2. Business productivity tips
3. Client success stories (anonymised)
4. Behind-the-scenes / company culture
5. Industry news commentary

## Risk Assessment

| Content Type | Risk | Rule |
|-------------|------|------|
| General insight / tips | `low` | Still requires approval |
| Client mention | `medium` | Must anonymise unless explicit consent |
| Financial data shared | `high` | Never post actual figures |
| Competitor mention | `high` | Legal review required |
| Political / religious | `high` | Never post |
| Promotional / sales | `medium` | Check tone guidelines |

## Post Templates

### LinkedIn (Thought Leadership)
```
[Hook — bold claim or question]

[2-3 supporting points with line breaks]

[Personal insight or lesson]

[Call to action]

#Hashtag1 #Hashtag2 #Hashtag3
```

### Twitter/X
```
[Strong hook ≤180 chars]

[Key point] 🧵

#Hashtag1 #Hashtag2
```

### Instagram
```
[Engaging caption — 150-200 words with emojis]

[Question to audience]

.
.
.
[Hashtag block — first comment]
```

## Rules
- NEVER post without `approval_required: true` flag being acknowledged
- NEVER share: client names without consent, financial specifics, internal metrics
- NEVER respond to controversy, political topics, or legal matters
- Brand voice: confident, helpful, forward-thinking — never aggressive or salesy
- Always check character limits before writing
- Add `DRY_RUN: true` note to all drafts when system is in dry run mode
- Archive all approved posts in `vault/Social/{platform}/`

## Example Output File
```yaml
---
skill: social_post
platform: linkedin
topic: AI Employee automation saves 4 hours/day
risk: low
approval_required: true
status: pending
created: 2026-03-15T10:00:00Z
dry_run: true
---

🤖 What if your email inbox managed itself?

Over the past month, our AI Employee has:
→ Auto-triaged 200+ emails
→ Drafted 47 replies for approval
→ Flagged 3 high-risk messages before they became problems

The result? 4+ hours saved every single day.

AI isn't replacing us — it's handling the repetitive work so we can focus on what matters.

What repetitive task would you automate first?

#AIAutomation #Productivity #AIEmployee #BusinessTools
```
