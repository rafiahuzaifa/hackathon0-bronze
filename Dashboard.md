# Dashboard

## Bank Balance
- Current Balance: $[Insert Balance]

## Pending Messages
- **12 emails** in `/Needs_Action` (10 real Gmail + 2 mock)

### Orders Requiring Action (4)
| Order | Vendor | Status | Action |
|---|---|---|---|
| #2834196 | Jenpharm | Shipped | Track & confirm delivery |
| #Z1637405 | Zellbury | Packed / Delivering today | Confirm receipt |
| #Z1639406 | Zellbury | Delivering today | Confirm receipt |
| #Z1643378 | Zellbury | Delivering today | Confirm receipt |

### Promotions (4) — No Action Needed
- 4x Temu promotional emails (price drops, discounts)

## Active Projects
- Jenpharm order #2834196 shipment tracking
- Zellbury orders delivery confirmation (3 orders)

## Flagged Items
- **Mock Invoice #4821: $750** — exceeds $500 threshold (Company Handbook Rule #2)

## System Status
- Gmail API: Connected (project `extreme-flux-487619-v0`, #839236699456)
- `gmail_watcher.py`: Operational (UTF-8 fix applied)
- Last scan: 2026-02-18 — 10 emails fetched

## Status Update
- **2026-02-18 (run 3)**: Gmail connected. Fetched 10 real emails. 4 orders need action (1 Jenpharm, 3 Zellbury). 4 Temu promos — no action. Plan.md updated with full action items.
- **2026-02-18 (run 2)**: Created 2 mock email test files. Pipeline validated.
- **2026-02-18 (run 1)**: Initial scan — `/Needs_Action` was empty.
