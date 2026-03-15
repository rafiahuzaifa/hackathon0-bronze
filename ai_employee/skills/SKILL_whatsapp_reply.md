---
skill: whatsapp_reply
version: 1.0
triggers:
  - new file in vault/Needs_Action/ matching WHATSAPP_*.md
input: WHATSAPP_{contact}_{timestamp}.md with message content and metadata
output: reply draft in vault/Pending_Approval/ (ALWAYS requires approval)
approval_required: true
max_length: 500
dry_run_safe: true
---

# SKILL: WhatsApp Reply Drafter

## Goal
Draft professional WhatsApp replies for business contacts. Always stage for approval — never send automatically.

## Steps
1. **Parse** contact name, message text, intent, screenshot path from input file
2. **Classify intent** (see Intent Table)
3. **Check** contact in whitelist (Company_Handbook.md §4.1)
4. **Draft reply** using appropriate template (≤500 characters)
5. **Set risk level** and `approval_required: true`
6. **Write** to `vault/Pending_Approval/WA_REPLY_{contact}_{timestamp}.md`
7. **Log** event

## Intent Classification & Templates

### pricing_inquiry
Keywords: price, cost, how much, rate, quote, package
```
Hi {name}! 👋 Thanks for reaching out to Demo Corp.

Our packages start from PKR {X}. I'd love to understand your needs better so I can share the right fit.

Could you tell me more about your project? I'll get back to you with a detailed proposal within 24 hours.
```

### partnership
Keywords: partner, collaborate, joint, opportunity, proposal
```
Hi {name}! Great to hear from you.

We're always open to meaningful partnerships. Could you share a brief overview of what you have in mind?

I'll review it and get back to you shortly. You can also email us at {email} for a more detailed discussion.
```

### complaint / issue
Keywords: problem, issue, not working, unhappy, refund, complaint
```
Hi {name}, I'm sorry to hear you're experiencing this. 🙏

I've flagged this to our team as a priority. We'll investigate and get back to you within {SLA} hours.

Your reference number is {ref}. Please don't hesitate to follow up if you need anything.
```

### general / hello
Keywords: hi, hello, hey, how are you, checking in
```
Hi {name}! 👋 Thanks for reaching out to Demo Corp.

How can I help you today? Feel free to share what you have in mind and I'll get back to you shortly.
```

### urgent
Keywords: urgent, ASAP, emergency, immediately, right now
```
Hi {name}, I see this is urgent! I've flagged it to our team immediately.

Someone will be in touch with you within {1-4} hours. If it's critical, please call {phone}.
```

## Rules
- Max 500 characters per message
- Always start with greeting: "Hi {name}!"
- Always end with next-step or closing
- Use friendly but professional tone (no slang)
- NEVER share: pricing without approval, personal staff info, internal processes
- NEVER promise specific outcomes or SLAs without checking capacity
- Business hours only: 09:00–18:00 PKT (add note if outside hours)
- No attachments unless explicitly approved
- Emoji: 1-2 per message maximum, use sparingly
- If intent unclear: ask one clarifying question, don't guess

## Output File Format
```yaml
---
skill: whatsapp_reply
contact: Ali Hassan
contact_number: +923001234567
original_message: "Hi, I wanted to know about your AI services pricing"
intent: pricing_inquiry
risk: medium
approval_required: true
char_count: 287
status: pending
created: 2026-03-15T14:30:00Z
dry_run: true
---

Hi Ali! 👋 Thanks for reaching out to Demo Corp.

Our AI automation packages start from PKR 15,000/month. I'd love to understand your needs so I can share the right fit.

Could you tell me more about your business? I'll get back to you with a detailed proposal within 24 hours.
```
