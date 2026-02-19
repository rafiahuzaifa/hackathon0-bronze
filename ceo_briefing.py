#!/usr/bin/env python3
"""
ceo_briefing.py — Monday Morning CEO Briefing Generator

Sunday cron triggers this to:
  1. Read Business_Goals.md, /Tasks/Done, Bank_Transactions.md
  2. Calculate revenue, expenses, net position
  3. Identify bottlenecks (overdue tasks, high-spend categories)
  4. Generate suggestions (cancel unused subs, follow-up on leads)
  5. Output Briefing.md in /Briefings with YAML frontmatter

Uses audit_logic patterns: multi-step calculation, threshold checks,
rule-based anomaly detection, structured markdown output.

CLI:
  python ceo_briefing.py                 # Generate briefing
  python ceo_briefing.py --test          # Run simulation tests
  python ceo_briefing.py --week 2026-W08 # Specific week label
"""

import os
import re
import sys
import glob
import logging
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
VAULT_DIR = Path("d:/hackathon0/hackathon/AI_Employee_Vault")
BRIEFINGS_DIR = VAULT_DIR / "Briefings"
TASKS_DONE_DIR = VAULT_DIR / "Tasks" / "Done"
BANK_FILE = VAULT_DIR / "Bank_Transactions.md"
GOALS_FILE = VAULT_DIR / "Business_Goals.md"
SOCIAL_GOALS_FILE = VAULT_DIR / "Social" / "Social_Goals.md"
DASHBOARD_FILE = VAULT_DIR / "Dashboard.md"
PLAN_FILE = VAULT_DIR / "Plan.md"
HANDBOOK_FILE = VAULT_DIR / "Company_Handbook.md"
ACCOUNTING_DIR = VAULT_DIR / "Accounting"
SOCIAL_SUMMARIES = VAULT_DIR / "Social" / "Summaries"

LOG_FILE = VAULT_DIR / "ceo_briefing.log"

# Thresholds (audit_logic patterns)
EXPENSE_FLAG_THRESHOLD = 500       # Flag expenses > $500
SUBSCRIPTION_WARN_THRESHOLD = 200  # Warn on subscriptions > $200/mo
LOW_BALANCE_THRESHOLD = 10000      # Warn if balance < $10k
REVENUE_TARGET_MONTHLY = 30000     # Monthly revenue target

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
        logging.StreamHandler(
            open(sys.stdout.fileno(), mode="w", encoding="utf-8", closefd=False)
            if sys.platform == "win32"
            else sys.stdout
        ),
    ],
)
logger = logging.getLogger("ceo_briefing")


# ---------------------------------------------------------------------------
# Step 1: Parse Bank Transactions
# ---------------------------------------------------------------------------
def parse_bank_transactions(filepath):
    """Parse Bank_Transactions.md into structured data."""
    transactions = []
    current_balance = 0.0
    total_income = 0.0
    total_expenses = 0.0

    if not filepath.exists():
        logger.warning(f"Bank file not found: {filepath}")
        return {
            "transactions": [],
            "balance": 0,
            "total_income": 0,
            "total_expenses": 0,
            "categories": {},
            "subscriptions": [],
            "flagged": [],
        }

    content = filepath.read_text(encoding="utf-8")

    # Parse table rows
    table_pattern = re.compile(
        r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(.+?)\s*\|\s*(\w+)\s*\|\s*([+-]?\$?[\d,.]+)\s*\|\s*\$?([\d,.]+)\s*\|"
    )

    for match in table_pattern.finditer(content):
        date_str, desc, category, amount_str, balance_str = match.groups()
        desc = desc.strip()
        category = category.strip().lower()

        # Parse amount
        amount_clean = amount_str.replace("$", "").replace(",", "").strip()
        if amount_clean == "—" or amount_clean == "":
            continue

        try:
            amount = float(amount_clean)
        except ValueError:
            continue

        try:
            balance = float(balance_str.replace(",", ""))
        except ValueError:
            balance = current_balance

        current_balance = balance

        txn = {
            "date": date_str,
            "description": desc,
            "category": category,
            "amount": amount,
            "balance": balance,
        }
        transactions.append(txn)

        if amount > 0:
            total_income += amount
        else:
            total_expenses += abs(amount)

    # Categorize expenses
    categories = {}
    subscriptions = []
    flagged = []

    for txn in transactions:
        cat = txn["category"]
        amt = abs(txn["amount"])

        if cat not in categories:
            categories[cat] = {"total": 0, "count": 0, "items": []}
        categories[cat]["total"] += amt
        categories[cat]["count"] += 1
        categories[cat]["items"].append(txn["description"])

        # Detect subscriptions
        if cat == "subscription":
            subscriptions.append(txn)

        # Flag large expenses (audit_logic pattern)
        if txn["amount"] < 0 and amt > EXPENSE_FLAG_THRESHOLD:
            flagged.append(txn)

    # Also parse the summary section for totals
    income_match = re.search(r"Total Income:\*?\*?\s*\$?([\d,.]+)", content)
    expense_match = re.search(r"Total Expenses:\*?\*?\s*\$?([\d,.]+)", content)
    balance_match = re.search(r"Current Balance:\*?\*?\s*\$?([\d,.]+)", content)

    if income_match:
        total_income = float(income_match.group(1).replace(",", ""))
    if expense_match:
        total_expenses = float(expense_match.group(1).replace(",", ""))
    if balance_match:
        current_balance = float(balance_match.group(1).replace(",", ""))

    return {
        "transactions": transactions,
        "balance": current_balance,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "categories": categories,
        "subscriptions": subscriptions,
        "flagged": flagged,
    }


# ---------------------------------------------------------------------------
# Step 2: Parse Completed Tasks
# ---------------------------------------------------------------------------
def parse_completed_tasks(tasks_dir):
    """Parse /Tasks/Done/*.md files with YAML frontmatter."""
    tasks = []

    if not tasks_dir.exists():
        logger.warning(f"Tasks/Done dir not found: {tasks_dir}")
        return tasks

    for filepath in sorted(tasks_dir.glob("*.md")):
        content = filepath.read_text(encoding="utf-8")

        task = {
            "file": filepath.name,
            "task": "",
            "completed": "",
            "category": "",
            "result": "",
            "body": "",
        }

        # Parse YAML frontmatter
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
        if fm_match:
            frontmatter, body = fm_match.groups()
            task["body"] = body.strip()

            for line in frontmatter.split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    task[key.strip()] = val.strip()
        else:
            task["body"] = content.strip()

        tasks.append(task)

    return tasks


# ---------------------------------------------------------------------------
# Step 3: Parse Business Goals
# ---------------------------------------------------------------------------
def parse_goals(filepath):
    """Extract goals and KPIs from Business_Goals.md."""
    if not filepath.exists():
        return {"focus_areas": [], "raw": "No goals file found."}

    content = filepath.read_text(encoding="utf-8")
    focus_areas = []

    # Extract numbered focus areas
    for match in re.finditer(
        r"\d+\.\s+\*\*(.+?)\*\*\s*—\s*(.+)", content
    ):
        focus_areas.append({"name": match.group(1), "target": match.group(2)})

    return {"focus_areas": focus_areas, "raw": content}


# ---------------------------------------------------------------------------
# Step 4: Bottleneck Detection (audit_logic pattern)
# ---------------------------------------------------------------------------
def detect_bottlenecks(bank_data, tasks, goals):
    """
    Identify bottlenecks using audit_logic patterns:
    - Threshold checks
    - Rule-based anomaly detection
    - Category analysis
    """
    bottlenecks = []

    # 1. Low balance warning
    if bank_data["balance"] < LOW_BALANCE_THRESHOLD:
        bottlenecks.append({
            "area": "Cash Flow",
            "severity": "HIGH",
            "issue": f"Balance ${bank_data['balance']:,.2f} below ${LOW_BALANCE_THRESHOLD:,} threshold",
            "impact": "May not cover next payroll cycle",
        })

    # 2. Revenue vs target
    revenue_pct = (
        (bank_data["total_income"] / REVENUE_TARGET_MONTHLY * 100)
        if REVENUE_TARGET_MONTHLY > 0
        else 0
    )
    if revenue_pct < 80:
        bottlenecks.append({
            "area": "Revenue",
            "severity": "MEDIUM",
            "issue": f"MTD revenue ${bank_data['total_income']:,.2f} is {revenue_pct:.0f}% of ${REVENUE_TARGET_MONTHLY:,} target",
            "impact": "May miss monthly revenue goal",
        })

    # 3. Subscription bloat
    sub_total = sum(abs(s["amount"]) for s in bank_data["subscriptions"])
    if sub_total > 1500:
        bottlenecks.append({
            "area": "Subscriptions",
            "severity": "MEDIUM",
            "issue": f"${sub_total:,.2f}/month in subscriptions ({len(bank_data['subscriptions'])} services)",
            "impact": "Recurring costs consuming significant revenue share",
        })

    # 4. High individual subscriptions
    for sub in bank_data["subscriptions"]:
        if abs(sub["amount"]) > SUBSCRIPTION_WARN_THRESHOLD:
            bottlenecks.append({
                "area": "Subscription",
                "severity": "LOW",
                "issue": f"{sub['description']}: ${abs(sub['amount']):,.2f}/month",
                "impact": "Consider if ROI justifies cost",
            })

    # 5. Flagged large expenses
    for txn in bank_data["flagged"]:
        bottlenecks.append({
            "area": "Expense",
            "severity": "MEDIUM",
            "issue": f"{txn['description']}: ${abs(txn['amount']):,.2f} exceeds ${EXPENSE_FLAG_THRESHOLD} threshold",
            "impact": "Requires manager approval per Company Handbook Rule #2",
        })

    # 6. Expense-to-income ratio
    if bank_data["total_income"] > 0:
        expense_ratio = bank_data["total_expenses"] / bank_data["total_income"] * 100
        if expense_ratio > 90:
            bottlenecks.append({
                "area": "Burn Rate",
                "severity": "HIGH",
                "issue": f"Expenses are {expense_ratio:.0f}% of income (${bank_data['total_expenses']:,.2f} / ${bank_data['total_income']:,.2f})",
                "impact": "Thin margins — risk of cash flow issues",
            })

    # 7. Incomplete tasks / goals alignment
    completed_categories = {}
    for t in tasks:
        cat = t.get("category", "other")
        completed_categories[cat] = completed_categories.get(cat, 0) + 1

    if completed_categories.get("project", 0) < 2:
        bottlenecks.append({
            "area": "Delivery",
            "severity": "LOW",
            "issue": f"Only {completed_categories.get('project', 0)} project tasks completed this period",
            "impact": "May affect client satisfaction and future revenue",
        })

    return bottlenecks


# ---------------------------------------------------------------------------
# Step 5: Generate Suggestions (audit_logic pattern)
# ---------------------------------------------------------------------------
def generate_suggestions(bank_data, tasks, goals, bottlenecks):
    """Generate actionable suggestions based on data analysis."""
    suggestions = []

    # 1. Subscription optimization
    subs = bank_data["subscriptions"]
    sub_total = sum(abs(s["amount"]) for s in subs)
    if sub_total > 1000:
        # Find least essential subscriptions
        low_value = [
            s for s in subs
            if abs(s["amount"]) < 150 and "zoom" not in s["description"].lower()
        ]
        if low_value:
            names = [s["description"] for s in low_value]
            savings = sum(abs(s["amount"]) for s in low_value)
            suggestions.append({
                "category": "Cost Reduction",
                "action": f"Review low-cost subscriptions: {', '.join(names)}",
                "potential_savings": f"${savings:,.2f}/month",
                "priority": "MEDIUM",
            })

    # 2. Revenue acceleration
    if bank_data["total_income"] < REVENUE_TARGET_MONTHLY:
        gap = REVENUE_TARGET_MONTHLY - bank_data["total_income"]
        suggestions.append({
            "category": "Revenue",
            "action": f"Close ${gap:,.2f} in additional revenue to hit monthly target",
            "potential_savings": f"+${gap:,.2f}",
            "priority": "HIGH",
        })

    # 3. Follow-up on completed projects
    project_tasks = [t for t in tasks if t.get("category") == "project"]
    for pt in project_tasks:
        if "phase" in pt.get("result", "").lower() or "follow" in pt.get("body", "").lower():
            suggestions.append({
                "category": "Business Development",
                "action": f"Follow up on {pt['task']} for expansion opportunity",
                "potential_savings": "Revenue upside",
                "priority": "MEDIUM",
            })

    # 4. Payroll optimization
    payroll_cat = bank_data["categories"].get("payroll", {})
    if payroll_cat.get("total", 0) > bank_data["total_income"] * 0.6:
        suggestions.append({
            "category": "Cost Optimization",
            "action": "Payroll exceeds 60% of revenue — review staffing levels or increase billing rates",
            "potential_savings": "Variable",
            "priority": "HIGH",
        })

    # 5. Cash reserve
    if bank_data["balance"] < LOW_BALANCE_THRESHOLD * 2:
        suggestions.append({
            "category": "Financial Health",
            "action": "Build cash reserve to at least 2x monthly expenses",
            "potential_savings": "Risk mitigation",
            "priority": "MEDIUM",
        })

    # 6. Goal alignment check
    for goal in goals.get("focus_areas", []):
        goal_name = goal["name"].lower()
        task_names = " ".join(t.get("task", "").lower() for t in tasks)
        if goal_name not in task_names and "lead" not in task_names:
            suggestions.append({
                "category": "Strategy",
                "action": f"No completed tasks aligned with goal: {goal['name']}",
                "potential_savings": "Strategic alignment",
                "priority": "LOW",
            })

    return suggestions


# ---------------------------------------------------------------------------
# Step 6: Generate Briefing Markdown
# ---------------------------------------------------------------------------
def generate_briefing(bank_data, tasks, goals, bottlenecks, suggestions, week_label=None):
    """Assemble the full Monday Morning CEO Briefing."""
    now = datetime.now()
    if not week_label:
        # Calculate ISO week
        week_label = now.strftime("%Y-W%W")

    period_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    period_end = now.strftime("%Y-%m-%d")

    # YAML frontmatter
    lines = [
        "---",
        f"title: Monday Morning CEO Briefing — {week_label}",
        f"generated: {now.isoformat()}",
        f"period: {period_start} to {period_end}",
        f"type: ceo_briefing",
        f"version: 1.0",
        f"status: generated",
        f"revenue_mtd: {bank_data['total_income']:.2f}",
        f"expenses_mtd: {bank_data['total_expenses']:.2f}",
        f"balance: {bank_data['balance']:.2f}",
        f"tasks_completed: {len(tasks)}",
        f"bottlenecks_count: {len(bottlenecks)}",
        f"suggestions_count: {len(suggestions)}",
        "---",
        "",
        f"# Monday Morning CEO Briefing",
        f"### {week_label} | Generated {now.strftime('%B %d, %Y at %I:%M %p')}",
        "",
        "---",
        "",
    ]

    # ── Executive Summary ──
    net = bank_data["total_income"] - bank_data["total_expenses"]
    net_sign = "+" if net >= 0 else ""
    revenue_pct = (
        (bank_data["total_income"] / REVENUE_TARGET_MONTHLY * 100)
        if REVENUE_TARGET_MONTHLY > 0
        else 0
    )

    high_bottlenecks = [b for b in bottlenecks if b["severity"] == "HIGH"]

    lines.extend([
        "## Executive Summary",
        "",
        f"- **Current Balance:** ${bank_data['balance']:,.2f}",
        f"- **MTD Revenue:** ${bank_data['total_income']:,.2f} ({revenue_pct:.0f}% of ${REVENUE_TARGET_MONTHLY:,} target)",
        f"- **MTD Expenses:** ${bank_data['total_expenses']:,.2f}",
        f"- **Net Position:** {net_sign}${abs(net):,.2f}",
        f"- **Tasks Completed:** {len(tasks)}",
        f"- **Bottlenecks:** {len(bottlenecks)} ({len(high_bottlenecks)} high severity)",
        "",
    ])

    # ── Financial Overview ──
    lines.extend([
        "## Financial Overview",
        "",
        "### Revenue Breakdown",
        "",
        "| Source | Amount | Date |",
        "|--------|--------|------|",
    ])

    income_txns = [t for t in bank_data["transactions"] if t["amount"] > 0]
    for txn in income_txns:
        lines.append(f"| {txn['description']} | ${txn['amount']:,.2f} | {txn['date']} |")

    lines.extend([
        f"| **Total** | **${bank_data['total_income']:,.2f}** | |",
        "",
        "### Expense Breakdown by Category",
        "",
        "| Category | Total | Items | % of Expenses |",
        "|----------|-------|-------|---------------|",
    ])

    # Sort categories by total
    sorted_cats = sorted(
        bank_data["categories"].items(),
        key=lambda x: x[1]["total"],
        reverse=True,
    )
    for cat, data in sorted_cats:
        if data["total"] > 0 and cat != "income" and cat != "—":
            pct = (data["total"] / bank_data["total_expenses"] * 100) if bank_data["total_expenses"] > 0 else 0
            lines.append(
                f"| {cat.title()} | ${data['total']:,.2f} | {data['count']} | {pct:.1f}% |"
            )

    lines.extend([
        f"| **Total** | **${bank_data['total_expenses']:,.2f}** | | **100%** |",
        "",
    ])

    # ── Subscriptions ──
    if bank_data["subscriptions"]:
        sub_total = sum(abs(s["amount"]) for s in bank_data["subscriptions"])
        lines.extend([
            "### Active Subscriptions",
            "",
            "| Service | Monthly Cost | Status |",
            "|---------|-------------|--------|",
        ])
        for sub in sorted(bank_data["subscriptions"], key=lambda s: abs(s["amount"]), reverse=True):
            flag = " **FLAG**" if abs(sub["amount"]) > SUBSCRIPTION_WARN_THRESHOLD else ""
            lines.append(f"| {sub['description']} | ${abs(sub['amount']):,.2f} | Active{flag} |")
        lines.extend([
            f"| **Total Subscriptions** | **${sub_total:,.2f}/month** | |",
            "",
        ])

    # ── Completed Tasks ──
    lines.extend([
        "## Tasks Completed This Period",
        "",
        "| Task | Category | Completed | Result |",
        "|------|----------|-----------|--------|",
    ])
    for task in tasks:
        lines.append(
            f"| {task['task']} | {task.get('category', 'N/A')} | {task.get('completed', 'N/A')} | {task.get('result', '')} |"
        )
    lines.append("")

    # ── Goals Progress ──
    lines.extend([
        "## Goals Progress",
        "",
    ])
    if goals.get("focus_areas"):
        lines.extend([
            "| Goal | Target | Status |",
            "|------|--------|--------|",
        ])
        for goal in goals["focus_areas"]:
            # Check if any tasks relate to this goal
            goal_lower = goal["name"].lower()
            related = [
                t for t in tasks
                if goal_lower in t.get("task", "").lower()
                or goal_lower in t.get("category", "").lower()
            ]
            status = f"{len(related)} tasks completed" if related else "No tasks yet"
            lines.append(f"| {goal['name']} | {goal['target']} | {status} |")
        lines.append("")
    else:
        lines.append("*No goals defined in Business_Goals.md.*\n")

    # ── Bottlenecks ──
    lines.extend([
        "## Bottlenecks & Risks",
        "",
        "| # | Severity | Area | Issue | Impact |",
        "|---|----------|------|-------|--------|",
    ])
    for i, bn in enumerate(sorted(bottlenecks, key=lambda b: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(b["severity"], 3)), 1):
        sev_icon = {"HIGH": "RED", "MEDIUM": "YELLOW", "LOW": "BLUE"}.get(bn["severity"], "")
        lines.append(
            f"| {i} | {sev_icon} {bn['severity']} | {bn['area']} | {bn['issue']} | {bn['impact']} |"
        )
    lines.append("")

    # ── Suggestions ──
    lines.extend([
        "## AI Suggestions",
        "",
        "| # | Category | Action | Potential Impact | Priority |",
        "|---|----------|--------|-----------------|----------|",
    ])
    for i, sug in enumerate(sorted(suggestions, key=lambda s: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(s["priority"], 3)), 1):
        lines.append(
            f"| {i} | {sug['category']} | {sug['action']} | {sug['potential_savings']} | {sug['priority']} |"
        )
    lines.append("")

    # ── Flagged Items ──
    if bank_data["flagged"]:
        lines.extend([
            "## Flagged Transactions (>$500)",
            "",
            "| Date | Description | Amount | Category |",
            "|------|-------------|--------|----------|",
        ])
        for txn in bank_data["flagged"]:
            lines.append(
                f"| {txn['date']} | {txn['description']} | ${abs(txn['amount']):,.2f} | {txn['category']} |"
            )
        lines.extend([
            "",
            "*Per Company Handbook Rule #2: Payments >$500 require manual approval.*",
            "",
        ])

    # ── Footer ──
    lines.extend([
        "---",
        "",
        f"*Generated by AI Employee CEO Briefing System*",
        f"*Data sources: Bank_Transactions.md, /Tasks/Done, Business_Goals.md*",
        f"*Next briefing: {(now + timedelta(days=7)).strftime('%Y-%m-%d')} (Sunday cron)*",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main: Orchestrate the briefing pipeline
# ---------------------------------------------------------------------------
def run_briefing(week_label=None):
    """Full briefing pipeline — multi-step calculation with validation."""
    logger.info("=" * 60)
    logger.info("CEO BRIEFING GENERATION — START")
    logger.info("=" * 60)

    errors = []

    # Step 1: Parse bank transactions
    logger.info("[1/6] Parsing Bank_Transactions.md...")
    bank_data = parse_bank_transactions(BANK_FILE)
    logger.info(
        f"  Balance: ${bank_data['balance']:,.2f} | "
        f"Income: ${bank_data['total_income']:,.2f} | "
        f"Expenses: ${bank_data['total_expenses']:,.2f}"
    )
    if not bank_data["transactions"]:
        errors.append("No transactions parsed from Bank_Transactions.md")

    # Step 2: Parse completed tasks
    logger.info("[2/6] Parsing /Tasks/Done...")
    tasks = parse_completed_tasks(TASKS_DONE_DIR)
    logger.info(f"  {len(tasks)} completed tasks found")

    # Step 3: Parse goals
    logger.info("[3/6] Parsing Business_Goals.md...")
    goals = parse_goals(GOALS_FILE)
    logger.info(f"  {len(goals['focus_areas'])} focus areas")

    # Step 4: Detect bottlenecks
    logger.info("[4/6] Running bottleneck analysis...")
    bottlenecks = detect_bottlenecks(bank_data, tasks, goals)
    high = sum(1 for b in bottlenecks if b["severity"] == "HIGH")
    logger.info(f"  {len(bottlenecks)} bottlenecks detected ({high} HIGH)")

    # Step 5: Generate suggestions
    logger.info("[5/6] Generating suggestions...")
    suggestions = generate_suggestions(bank_data, tasks, goals, bottlenecks)
    logger.info(f"  {len(suggestions)} suggestions generated")

    # Step 6: Assemble and write briefing
    logger.info("[6/6] Generating briefing document...")
    briefing_md = generate_briefing(
        bank_data, tasks, goals, bottlenecks, suggestions, week_label
    )

    # Ensure directory exists
    BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    filename = f"Briefing_{now.strftime('%Y-%m-%d')}_{now.strftime('%H%M%S')}.md"
    filepath = BRIEFINGS_DIR / filename
    filepath.write_text(briefing_md, encoding="utf-8")

    logger.info(f"  Briefing saved: {filepath}")
    logger.info(f"  Size: {len(briefing_md)} chars, {briefing_md.count(chr(10))} lines")

    # Validation (Ralph Wiggum multi-step check)
    checks = {
        "has_frontmatter": briefing_md.startswith("---"),
        "has_executive_summary": "Executive Summary" in briefing_md,
        "has_financial_overview": "Financial Overview" in briefing_md,
        "has_bottlenecks": "Bottlenecks" in briefing_md,
        "has_suggestions": "AI Suggestions" in briefing_md,
        "has_tasks": "Tasks Completed" in briefing_md,
        "has_goals": "Goals Progress" in briefing_md,
        "balance_parsed": bank_data["balance"] > 0 or not bank_data["transactions"],
        "file_written": filepath.exists(),
    }

    all_passed = all(checks.values())
    for name, result in checks.items():
        status = "PASS" if result else "FAIL"
        logger.info(f"  Validation: {status} — {name}")

    if errors:
        for err in errors:
            logger.warning(f"  Warning: {err}")

    logger.info("=" * 60)
    logger.info(
        f"BRIEFING COMPLETE: {filepath.name} | "
        f"{'ALL CHECKS PASSED' if all_passed else 'SOME CHECKS FAILED'}"
    )
    logger.info("=" * 60)

    return {
        "filepath": str(filepath),
        "filename": filename,
        "checks": checks,
        "all_passed": all_passed,
        "bank_data": bank_data,
        "tasks": tasks,
        "goals": goals,
        "bottlenecks": bottlenecks,
        "suggestions": suggestions,
        "briefing_md": briefing_md,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Cron Helper: Sunday scheduling
# ---------------------------------------------------------------------------
def setup_cron_schedule():
    """Print crontab entry for Sunday evening briefing generation."""
    script_path = Path(__file__).resolve()
    python_path = sys.executable

    cron_line = f"0 20 * * 0 {python_path} {script_path} >> {LOG_FILE} 2>&1"
    pm2_config = {
        "name": "ceo-briefing",
        "script": str(script_path),
        "interpreter": python_path,
        "cron_restart": "0 20 * * 0",
        "autorestart": False,
    }

    print("\n--- Sunday Cron Setup ---")
    print(f"\nOption 1: crontab (add with `crontab -e`):")
    print(f"  {cron_line}")
    print(f"\nOption 2: PM2 ecosystem.config.js entry:")
    print(f"  {pm2_config}")
    print(f"\nOption 3: Windows Task Scheduler:")
    print(f'  schtasks /create /tn "CEO_Briefing" /tr "{python_path} {script_path}" /sc weekly /d SUN /st 20:00')
    print()


# ---------------------------------------------------------------------------
# Test Suite with Ralph Wiggum Loop
# ---------------------------------------------------------------------------
def run_tests():
    """Simulation test suite — iterate until all pass."""
    MAX_ATTEMPTS = 3
    success = False

    for attempt in range(1, MAX_ATTEMPTS + 1):
        logger.info(f"\nRalph Wiggum Iteration #{attempt}")

        passed = 0
        failed = 0
        total = 0

        def check(condition, name):
            nonlocal passed, failed, total
            total += 1
            if condition:
                passed += 1
                logger.info(f"  PASS: {name}")
            else:
                failed += 1
                logger.info(f"  FAIL: {name}")

        logger.info("=" * 60)
        logger.info("CEO BRIEFING — SIMULATION TEST SUITE")
        logger.info("=" * 60)

        # ── Test 1: Bank Transaction Parsing ──
        logger.info("\n[1/10] Bank Transaction Parsing")
        bank = parse_bank_transactions(BANK_FILE)
        check(len(bank["transactions"]) > 0, f"Parsed {len(bank['transactions'])} transactions")
        check(bank["balance"] > 0, f"Balance: ${bank['balance']:,.2f}")
        check(bank["total_income"] > 0, f"Total income: ${bank['total_income']:,.2f}")
        check(bank["total_expenses"] > 0, f"Total expenses: ${bank['total_expenses']:,.2f}")
        check(bank["total_income"] == 28200.0, f"Income matches $28,200")
        check(bank["total_expenses"] == 26324.5, f"Expenses match $26,324.50")
        check(bank["balance"] == 26375.5, f"Balance matches $26,375.50")

        # ── Test 2: Category Breakdown ──
        logger.info("\n[2/10] Category Breakdown")
        check("subscription" in bank["categories"], "Subscription category found")
        check("payroll" in bank["categories"], "Payroll category found")
        check("rent" in bank["categories"], "Rent category found")
        sub_total = bank["categories"].get("subscription", {}).get("total", 0)
        check(sub_total > 0, f"Subscription total: ${sub_total:,.2f}")

        # ── Test 3: Subscription Detection ──
        logger.info("\n[3/10] Subscription Detection")
        check(len(bank["subscriptions"]) >= 5, f"Found {len(bank['subscriptions'])} subscriptions")
        sub_names = [s["description"] for s in bank["subscriptions"]]
        check(any("AWS" in n for n in sub_names), "AWS subscription detected")
        check(any("Slack" in n for n in sub_names), "Slack subscription detected")

        # ── Test 4: Flagged Expenses ──
        logger.info("\n[4/10] Flagged Expenses (>$500)")
        check(len(bank["flagged"]) > 0, f"Found {len(bank['flagged'])} flagged items")
        flagged_amts = [abs(f["amount"]) for f in bank["flagged"]]
        check(all(a > EXPENSE_FLAG_THRESHOLD for a in flagged_amts), "All flagged > $500")
        check(any("Office Supplies" in f["description"] for f in bank["flagged"]),
              "Office Supplies #4821 ($750) flagged")

        # ── Test 5: Tasks Parsing ──
        logger.info("\n[5/10] Completed Tasks Parsing")
        tasks = parse_completed_tasks(TASKS_DONE_DIR)
        check(len(tasks) >= 5, f"Found {len(tasks)} completed tasks")
        task_names = [t["task"] for t in tasks]
        check(any("Acme" in n for n in task_names), "Acme Corp task found")
        check(any("Widget" in n for n in task_names), "Widget Inc task found")
        check(any("payroll" in n.lower() for n in task_names), "Payroll task found")

        # ── Test 6: Goals Parsing ──
        logger.info("\n[6/10] Goals Parsing")
        goals = parse_goals(GOALS_FILE)
        check(len(goals["focus_areas"]) >= 3, f"Found {len(goals['focus_areas'])} focus areas")
        goal_names = [g["name"] for g in goals["focus_areas"]]
        check("Lead Generation" in goal_names, "Lead Generation goal found")
        check("Thought Leadership" in goal_names, "Thought Leadership goal found")

        # ── Test 7: Bottleneck Detection ──
        logger.info("\n[7/10] Bottleneck Detection")
        bottlenecks = detect_bottlenecks(bank, tasks, goals)
        check(len(bottlenecks) > 0, f"Detected {len(bottlenecks)} bottlenecks")
        bn_areas = [b["area"] for b in bottlenecks]
        check(any("Burn Rate" in a or "Expense" in a for a in bn_areas),
              "Financial bottleneck detected")
        severities = [b["severity"] for b in bottlenecks]
        check("HIGH" in severities or "MEDIUM" in severities, "Severity levels assigned")

        # ── Test 8: Suggestion Generation ──
        logger.info("\n[8/10] Suggestion Generation")
        suggestions = generate_suggestions(bank, tasks, goals, bottlenecks)
        check(len(suggestions) > 0, f"Generated {len(suggestions)} suggestions")
        sug_cats = [s["category"] for s in suggestions]
        check(any("Revenue" in c or "Cost" in c or "Business" in c for c in sug_cats),
              "Actionable categories present")
        check(all("priority" in s for s in suggestions), "All suggestions have priority")

        # ── Test 9: Full Briefing Generation ──
        logger.info("\n[9/10] Full Briefing Generation")
        result = run_briefing(week_label="2026-W08-TEST")
        check(result["all_passed"], "All internal validation checks passed")
        check(result["filepath"].endswith(".md"), "Briefing is .md file")
        check(os.path.exists(result["filepath"]), "Briefing file exists on disk")

        md = result["briefing_md"]
        check(md.startswith("---"), "Has YAML frontmatter")
        check("Executive Summary" in md, "Has Executive Summary section")
        check("Financial Overview" in md, "Has Financial Overview section")
        check("Revenue Breakdown" in md, "Has Revenue Breakdown table")
        check("Expense Breakdown" in md, "Has Expense Breakdown table")
        check("Active Subscriptions" in md, "Has Subscriptions section")
        check("Tasks Completed" in md, "Has Tasks section")
        check("Goals Progress" in md, "Has Goals section")
        check("Bottlenecks" in md, "Has Bottlenecks section")
        check("AI Suggestions" in md, "Has AI Suggestions section")
        check("$500" in md, "References $500 threshold")
        check("Company Handbook" in md, "References Company Handbook")
        check("revenue_mtd: 28200" in md, "YAML has correct revenue")
        check("balance: 26375" in md, "YAML has correct balance")

        # ── Test 10: Multi-Step Calculation Validation ──
        logger.info("\n[10/10] Multi-Step Calculation Validation")
        net = bank["total_income"] - bank["total_expenses"]
        check(abs(net - 1875.5) < 0.01, f"Net position: ${net:,.2f} = $1,875.50")

        revenue_pct = bank["total_income"] / REVENUE_TARGET_MONTHLY * 100
        check(abs(revenue_pct - 94.0) < 1, f"Revenue % of target: {revenue_pct:.0f}%")

        expense_ratio = bank["total_expenses"] / bank["total_income"] * 100
        check(expense_ratio > 90, f"Expense ratio: {expense_ratio:.1f}% (triggers bottleneck)")

        sub_total_all = sum(abs(s["amount"]) for s in bank["subscriptions"])
        check(sub_total_all > 1500, f"Subscription total: ${sub_total_all:,.2f} (triggers warning)")

        # ── Results ──
        logger.info("\n" + "=" * 60)
        logger.info(f"RESULTS: {passed} passed, {failed} failed, {total} total")
        logger.info("=" * 60)

        if failed == 0:
            success = True
            break

    if success:
        logger.info(f"\nAll tests passed!")
        return True
    else:
        logger.info(f"\nTests failing after {MAX_ATTEMPTS} attempts.")
        return False


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    args = sys.argv[1:]

    if "--test" in args:
        ok = run_tests()
        sys.exit(0 if ok else 1)
    elif "--cron" in args:
        setup_cron_schedule()
    else:
        week = None
        for i, a in enumerate(args):
            if a == "--week" and i + 1 < len(args):
                week = args[i + 1]
        result = run_briefing(week_label=week)
        if result["all_passed"]:
            print(f"\nBriefing generated: {result['filename']}")
        else:
            print(f"\nBriefing generated with warnings: {result['filename']}")
            sys.exit(1)
