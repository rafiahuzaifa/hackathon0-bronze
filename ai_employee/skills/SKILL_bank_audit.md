---
skill: bank_audit
version: 1.0
triggers:
  - new CSV file in uploads/bank/
  - daily cron: 08:00
  - manual trigger
input: CSV file with columns: date, description, amount, type (credit/debit), balance
output:
  - vault/Needs_Action/BANK_ALERT_{date}.md (if anomalies found)
  - vault/Logs/bank_audit_{date}.json
approval_required: false
dry_run_safe: true
---

# SKILL: Bank Transaction Audit

## Goal
Analyse bank transaction CSVs for anomalies, calculate monthly P&L, track subscriptions, and flag suspicious activity.

## Expected CSV Format
```csv
date,description,amount,type,balance,reference
2026-03-15,Stripe Payment,5000.00,credit,26500.00,TXN_001
2026-03-15,Adobe Creative Cloud,2999.00,debit,23501.00,TXN_002
```

## Steps

1. **Load** CSV file — handle encoding errors, skip header row
2. **Validate** columns — alert if required columns missing
3. **Separate** credits (income) and debits (expenses)
4. **Calculate monthly totals**:
   - `income_total` = sum of all credits this month
   - `expenses_total` = sum of all debits this month
   - `net` = income - expenses
5. **Run anomaly detection** (see Anomaly Rules below)
6. **Identify subscriptions** — recurring monthly charges from same vendor
7. **Compare** to previous month (if prior CSV exists)
8. **Generate report** and write to `vault/Logs/bank_audit_{YYYY-MM-DD}.json`
9. **If anomalies found** → write `vault/Needs_Action/BANK_ALERT_{YYYY-MM-DD}.md`
10. **Update** Dashboard.md finance section

## Anomaly Detection Rules

### ROUND_AMOUNT_FLAG
Trigger: debit amount is exactly 1000, 2000, 5000, 10000, 50000 (round numbers)
Risk: medium — common in fraudulent transactions
Action: flag for review, do not block

### DUPLICATE_FLAG
Trigger: same description + amount + type within 48 hours
Risk: high — likely duplicate charge
Action: flag immediately, halt if auto-payment enabled

### UNKNOWN_VENDOR_FLAG
Trigger: vendor name not in known-vendors list AND amount > PKR 500
Risk: medium — could be subscription started without approval
Action: flag, add to "unrecognised vendors" list

### HIGH_VALUE_FLAG
Trigger: single debit > PKR 10,000
Risk: high — requires review
Action: notify immediately

### SPIKE_FLAG
Trigger: any category expense > 3× 30-day average
Risk: medium — unusual spending pattern
Action: flag with comparison data

### SUBSCRIPTION_DRIFT_FLAG
Trigger: recurring charge changed amount by >5%
Risk: low-medium — price increase without notice
Action: note in subscription tracker

## Subscription Tracker
Maintain a running list of detected subscriptions:
```json
{
  "subscriptions": [
    {"vendor": "Adobe Creative Cloud", "amount": 2999, "currency": "PKR", "frequency": "monthly", "last_seen": "2026-03-15"},
    {"vendor": "AWS", "amount": 1200, "currency": "PKR", "frequency": "monthly", "last_seen": "2026-03-14"}
  ],
  "total_monthly_subscriptions": 4199
}
```

## Alert File Format
```yaml
---
skill: bank_audit
date: 2026-03-15
csv_file: transactions_mar2026.csv
rows_processed: 238
anomalies_found: 3
total_flags: [ROUND_AMOUNT_FLAG, ROUND_AMOUNT_FLAG, DUPLICATE_FLAG]
income_month: 8500
expenses_month: 3200
net_month: 5300
status: needs_review
---

# ⚠️ Bank Audit Alert — 2026-03-15

## Anomalies Detected

### 🟡 ROUND_AMOUNT_FLAG (2 instances)
- TXN_045: PKR 5,000 debit — "Cash Withdrawal" — 2026-03-12
- TXN_078: PKR 10,000 debit — "Transfer" — 2026-03-14

### 🔴 DUPLICATE_FLAG (1 instance)
- TXN_089 + TXN_090: PKR 2,999 — "Adobe Creative Cloud" — within 24 hours

## Action Required
- [ ] Review TXN_045 and TXN_078 cash withdrawals
- [ ] Dispute duplicate charge TXN_090 with bank
```

## Rules
- ALWAYS process in DRY_RUN mode (no bank API calls, only analysis)
- Never store raw bank credentials
- Archive processed CSVs to `uploads/bank/processed/`
- Retain audit logs for 90 days minimum
- PKR amounts always formatted with commas: PKR 10,000
- Alert threshold for immediate notification: HIGH_VALUE_FLAG or DUPLICATE_FLAG
