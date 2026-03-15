---
skill: invoice_generate
version: 1.0
triggers:
  - email intent = invoice AND action = generate_invoice
  - manual trigger: vault/Needs_Action/INVOICE_REQUEST_*.md
input: client name, amount, services, due_date
output:
  - vault/Pending_Approval/INVOICE_{client}_{date}.md (markdown invoice)
  - vault/Pending_Approval/EMAIL_INVOICE_{client}_{date}.md (delivery email draft)
approval_required: true
dry_run_safe: true
---

# SKILL: Invoice Generator

## Goal
Generate professional invoices from client requests and draft delivery emails. Both the invoice and the sending email require human approval.

## Steps
1. **Extract** invoice details from input: client, services, amounts, due date
2. **Look up** client in Business_Goals.md for address, standard rates
3. **Generate invoice number**: INV-{YYYY}-{sequential_id}
4. **Calculate**: subtotal, tax (if applicable), total
5. **Write** markdown invoice to `vault/Pending_Approval/INVOICE_{client}_{YYYYMMDD}.md`
6. **Draft** delivery email to `vault/Pending_Approval/EMAIL_INVOICE_{client}_{YYYYMMDD}.md`
7. **Log** generation event

## Invoice Template
```markdown
---
skill: invoice_generate
invoice_number: INV-2026-089
client: Acme Corp
amount: 75000
currency: PKR
due_date: 2026-04-01
status: pending_approval
approval_required: true
---

# INVOICE

**Demo Corp**
123 Business Street, Karachi, Pakistan
ai@democorp.com | +92-300-1234567

---

**INVOICE #:** INV-2026-089
**DATE:** 2026-03-15
**DUE DATE:** 2026-04-01

---

**BILL TO:**
Acme Corp
Contact: John Smith
john@acme.com

---

| # | Description | Qty | Rate (PKR) | Amount (PKR) |
|---|-------------|-----|-----------|--------------|
| 1 | AI Employee Setup & Integration | 1 | 50,000 | 50,000 |
| 2 | Monthly Maintenance (March 2026) | 1 | 25,000 | 25,000 |

---

**SUBTOTAL:** PKR 75,000
**TAX (0%):** PKR 0
**TOTAL DUE:** PKR 75,000

---

**PAYMENT INSTRUCTIONS:**
Bank: HBL | Account: 0123-456789-01 | Title: Demo Corp

*Payment due within 15 days. Late payments subject to 2% monthly charge.*

Thank you for your business! 🙏
```

## Delivery Email Template
```
Subject: Invoice #INV-2026-089 — Demo Corp

Dear John,

Please find attached Invoice #INV-2026-089 for services rendered in March 2026.

**Amount Due:** PKR 75,000
**Due Date:** 1st April 2026

Payment can be made via bank transfer to:
HBL | Account: 0123-456789-01 | Title: Demo Corp

Please don't hesitate to reach out if you have any questions.

Best regards,
Demo Corp
```

## Rules
- NEVER send invoice without explicit human approval
- Invoice numbers must be sequential (check last invoice in vault)
- Always include payment instructions and due date
- Tax: apply 0% by default unless client profile specifies otherwise
- Currency: PKR by default
- Archive approved invoices to `vault/Accounting/Invoices/`
- Late payment terms: always include in invoice footer
