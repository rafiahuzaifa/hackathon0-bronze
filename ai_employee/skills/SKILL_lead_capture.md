---
skill: lead_capture
version: 1.0
triggers:
  - intent detected in EMAIL, WHATSAPP, or LINKEDIN message
  - keywords: pricing, quote, hire, buy, interested, proposal, services, package
input: any Needs_Action/*.md file with high-intent signals
output: vault/Needs_Action/LEAD_{source}_{contact}_{timestamp}.md
approval_required: false
dry_run_safe: true
---

# SKILL: Lead Capture

## Goal
Detect sales/business intent in any incoming message, create a structured lead file, score the lead, and draft initial follow-up action.

## Steps
1. **Detect** trigger keywords in source message
2. **Extract** contact info: name, company, email/phone/platform
3. **Score lead** 1–10 (see Lead Scoring)
4. **Create lead file** with full metadata
5. **Draft follow-up action** based on intent + score
6. **Write** `vault/Needs_Action/LEAD_{source}_{contact}_{timestamp}.md`
7. **If score ≥ 7** → also create `vault/Pending_Approval/FOLLOWUP_{contact}.md`
8. **Log** lead capture event

## Trigger Keywords
```
High intent (score +3): pricing, quote, hire, buy now, ready to start, invoice me, sign up
Medium intent (score +2): interested, tell me more, how does it work, demo, proposal
Low intent (score +1): curious, exploring, checking out, saw your post
Negative (score -2): just browsing, not buying, student project, for free
```

## Lead Scoring (1–10)

| Signal | Points |
|--------|--------|
| Explicit pricing request | +3 |
| Budget mentioned | +2 |
| Timeline mentioned ("by next month") | +2 |
| Decision maker title (CEO, Director, Founder) | +2 |
| Company name provided | +1 |
| Referral ("told by X") | +2 |
| Multiple messages in 24h | +1 |
| Engagement on social post | +1 |
| Large company (>50 employees) | +1 |
| Previous interaction | +1 |

**Score interpretation:**
- 8–10: Hot lead → immediate follow-up draft
- 5–7: Warm lead → draft follow-up, queue for 24h
- 1–4: Cold lead → add to nurture list

## Lead File Format
```yaml
---
skill: lead_capture
source: whatsapp|email|linkedin|twitter
contact_name: Ali Hassan
contact_company: TechCorp Pvt Ltd
contact_email: ali@techcorp.pk
contact_phone: +923001234567
contact_platform: WhatsApp
lead_score: 8
lead_temperature: hot
intent: pricing_inquiry
original_message: "Hi, we need AI automation for our 50-person team. What are your packages?"
keywords_matched: [pricing, packages, team]
created: 2026-03-15T14:30:00Z
follow_up_drafted: true
follow_up_file: Pending_Approval/FOLLOWUP_ali_hassan_20260315.md
status: new
---

# 🔥 Hot Lead — Ali Hassan (TechCorp Pvt Ltd)
**Source:** WhatsApp | **Score:** 8/10 | **Detected:** 2026-03-15 14:30

## Contact Details
- **Name:** Ali Hassan
- **Company:** TechCorp Pvt Ltd
- **Platform:** WhatsApp (+923001234567)

## Original Message
> "Hi, we need AI automation for our 50-person team. What are your packages?"

## Intent Analysis
- Primary intent: pricing_inquiry
- Keywords: pricing, packages, team (50 people = enterprise tier)
- Decision signals: "we need" (committed language), team size mentioned

## Recommended Action
1. Send pricing deck within 2 hours (hot lead SLA)
2. Schedule discovery call
3. Prepare custom proposal for 50-person team

## Next Step
→ Review and approve follow-up in Pending_Approval/FOLLOWUP_ali_hassan_20260315.md
```

## CRM Note Format
Append to `vault/Business_Goals.md` under "Active Pipeline":
```
| Ali Hassan | TechCorp | WhatsApp | 8/10 | Pricing | 2026-03-15 | Follow-up drafted |
```

## Rules
- Capture ALL leads, even low-score ones (add to nurture list)
- Never discard lead data — always create lead file
- De-duplicate: check if contact already in pipeline before creating new lead
- GDPR-style note: data used only for business development purposes
- Hot leads (score ≥ 8): immediate notification to human
- Follow-up timing: hot = 2h, warm = 24h, cold = 72h
