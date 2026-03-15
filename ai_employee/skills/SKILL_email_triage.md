---
skill: email_triage
version: 1.0
triggers:
  - new file in vault/Needs_Action/ matching EMAIL_*.md
  - manual trigger via dashboard
input: EMAIL_{id}.md with YAML frontmatter (sender, subject, snippet, intent, risk)
output: reply drafted in Pending_Approval/ OR alert in Needs_Action/ OR moved to Done/
dry_run_safe: true
---

# SKILL: Email Triage

## Goal
Classify incoming emails, auto-reply to safe ones, escalate risky ones to human review. Never send emails to unknown senders without approval.

## Context
Read email metadata from YAML frontmatter. Reference `vault/Company_Handbook.md` for tone and rules. Check `vault/Business_Goals.md` for known clients.

## Steps

1. **Parse** YAML frontmatter from input file: sender, subject, snippet, intent, risk, thread_id, labels
2. **Enrich** — check if sender is in known-contacts list (Business_Goals.md client list)
3. **Classify intent** using keywords:
   - `invoice|payment|bill|receipt` → `invoice`
   - `partnership|collaboration|proposal|opportunity` → `partnership`
   - `urgent|asap|immediately|critical` → `urgent`
   - `hiring|job|position|cv|resume` → `recruiting`
   - `support|help|issue|problem|bug` → `support`
   - default → `general`
4. **Score risk** (see Risk Scoring table below)
5. **Route by risk**:
   - `low` → draft auto-reply → write to `vault/Pending_Approval/EMAIL_REPLY_{id}.md` with `approval_required: false`
   - `medium` → draft reply → write to `vault/Pending_Approval/EMAIL_REPLY_{id}.md` with `approval_required: true`
   - `high` → write `vault/Needs_Action/ALERT_EMAIL_{id}.md`, set `status: escalated`, do NOT draft reply
6. **Update** original file: add `status`, `intent`, `risk`, `action_taken` fields
7. **Move** original to `vault/Done/EMAIL_{id}.md`
8. **Log** to `vault/Logs/YYYY-MM-DD.json`

## Risk Scoring

| Condition | Risk Level |
|-----------|-----------|
| Known sender + general / support query | `low` |
| Unknown sender, any intent | `medium` |
| Payment or invoice mentioned | `medium` |
| Amount > PKR 10,000 mentioned | `high` |
| Keywords: legal, lawsuit, demand, refund, chargeback | `high` |
| Urgent + unknown sender | `high` |
| Partnership from Fortune-500 or known brand | `medium` |
| Spam indicators (unsubscribe, bulk) | `low` (archive, no reply) |

## Reply Format (Company_Handbook tone)
```
Subject: Re: {original_subject}

Dear {first_name},

Thank you for reaching out to Demo Corp.

{context-specific body — 2-3 sentences}

Best regards,
AI Employee
Demo Corp | ai@democorp.com
```

## Rules
- NEVER auto-send to unknown senders without human approval
- ALWAYS use professional tone (see Company_Handbook.md §2.1)
- Flag: legal, lawsuit, refund, chargeback → immediate escalation
- Flag: payment request > PKR 10,000 → high risk regardless of sender
- Partnership proposals → minimum medium risk (always human review)
- Response time targets: urgent = 1h, high-intent = 4h, general = 24h
- Max email body: 300 words for auto-replies
- Include thread_id in all replies to maintain conversation context

## Examples
```yaml
# INPUT (low risk — auto reply drafted)
sender: support@stripe.com
subject: Invoice #INV-2024-089 receipt
intent: invoice
known_sender: true
risk: low
→ ACTION: draft receipt acknowledgment, write to Pending_Approval with approval_required=false

# INPUT (medium risk — awaits human)
sender: ceo@newcompany.com
subject: Partnership opportunity
intent: partnership
known_sender: false
risk: medium
→ ACTION: draft partnership response, write to Pending_Approval with approval_required=true

# INPUT (high risk — escalate)
sender: unknown@domain.com
subject: Legal notice — demand for payment
intent: urgent
keywords_found: [legal, demand, payment]
risk: high
→ ACTION: write ALERT file, do NOT draft reply, notify human immediately
```
