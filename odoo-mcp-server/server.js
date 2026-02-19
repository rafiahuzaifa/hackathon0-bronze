#!/usr/bin/env node

/**
 * Odoo MCP Server — Accounting Integration for AI Employee
 *
 * Connects to Odoo 19+ Community via JSON-RPC.
 * All write operations create DRAFT entries only.
 *
 * Tools:
 *   - test_connection:    Verify Odoo connectivity
 *   - create_invoice:     Create a draft customer invoice
 *   - log_transaction:    Log an income/expense transaction
 *   - get_invoices:       Read invoice summary (draft/posted)
 *   - get_balance:        Get receivable/payable balances
 *   - read_accounting:    Read /Accounting/Current_Month.md
 *   - generate_audit:     Generate weekly audit prompt for Claude
 *
 * Env vars:
 *   ODOO_URL, ODOO_DB, ODOO_USER, ODOO_PASSWORD, ODOO_SIMULATE
 */

const { McpServer } = require("@modelcontextprotocol/sdk/server/mcp.js");
const {
  StdioServerTransport,
} = require("@modelcontextprotocol/sdk/server/stdio.js");
const { z } = require("zod");
const fs = require("fs");
const path = require("path");
const { OdooClient } = require("./odoo-client.js");

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------
const VAULT_DIR = "d:/hackathon0/hackathon/AI_Employee_Vault";
const ACCOUNTING_DIR = path.join(VAULT_DIR, "Accounting");
const CURRENT_MONTH_FILE = path.join(ACCOUNTING_DIR, "Current_Month.md");
const AUDIT_DIR = path.join(ACCOUNTING_DIR, "Audits");
const LOG_FILE = path.join(__dirname, "odoo-mcp.log");

[ACCOUNTING_DIR, AUDIT_DIR].forEach((d) => fs.mkdirSync(d, { recursive: true }));

function log(level, msg, data = null) {
  const ts = new Date().toISOString();
  const entry = `[${ts}] [${level}] ${msg}${data ? " " + JSON.stringify(data) : ""}`;
  fs.appendFileSync(LOG_FILE, entry + "\n", "utf-8");
}

// ---------------------------------------------------------------------------
// Odoo Client Instance
// ---------------------------------------------------------------------------
const odoo = new OdooClient();

// ---------------------------------------------------------------------------
// MCP Server
// ---------------------------------------------------------------------------
const server = new McpServer({
  name: "odoo-accounting",
  version: "1.0.0",
});

// ── Tool: test_connection ──
server.tool(
  "test_connection",
  "Test connection to the Odoo instance and verify credentials",
  {},
  async () => {
    log("INFO", "test_connection called");
    const result = await odoo.testConnection();
    return {
      content: [
        {
          type: "text",
          text: result.status === "ok"
            ? [
                `✅ Odoo connection successful`,
                `  Server: ${result.server}`,
                `  Database: ${result.db}`,
                `  UID: ${result.uid}`,
                result.version ? `  Version: ${result.version}` : "",
                result.simulated ? `  Mode: SIMULATED` : `  Mode: LIVE`,
              ]
                .filter(Boolean)
                .join("\n")
            : `❌ Connection failed: ${result.error}`,
        },
      ],
    };
  }
);

// ── Tool: create_invoice ──
server.tool(
  "create_invoice",
  "Create a DRAFT customer invoice in Odoo. Does NOT post — requires manual approval.",
  {
    partner: z.string().describe("Customer/partner name (e.g. 'Acme Corp')"),
    lines: z
      .array(
        z.object({
          description: z.string().describe("Line item description"),
          quantity: z.number().default(1).describe("Quantity"),
          price: z.number().describe("Unit price"),
        })
      )
      .describe("Invoice line items"),
    reference: z
      .string()
      .optional()
      .describe("Invoice reference (e.g. 'Q1-Services')"),
  },
  async ({ partner, lines, reference }) => {
    log("INFO", "create_invoice called", { partner, lines: lines.length });

    try {
      const result = await odoo.createDraftInvoice(partner, lines, reference);

      // Update Current_Month.md
      appendToCurrentMonth(
        `| ${new Date().toISOString().split("T")[0]} | Invoice #${result.id} | ${partner} | $${result.total.toFixed(2)} | Draft |`
      );

      return {
        content: [
          {
            type: "text",
            text: [
              `✅ Draft invoice created${result.simulated ? " (SIMULATED)" : ""}`,
              ``,
              `**Invoice ID:** ${result.id}`,
              `**Partner:** ${result.partner}`,
              `**Lines:** ${result.lines}`,
              `**Total:** $${result.total.toFixed(2)}`,
              `**Status:** DRAFT (requires manual posting)`,
              `**Reference:** ${result.ref}`,
              ``,
              `Entry logged to /Accounting/Current_Month.md`,
            ].join("\n"),
          },
        ],
      };
    } catch (err) {
      log("ERROR", `create_invoice failed: ${err.message}`);
      return {
        content: [
          {
            type: "text",
            text: `❌ Failed to create invoice: ${err.message}\n\nRetries exhausted (3/3). Check Odoo connection.`,
          },
        ],
      };
    }
  }
);

// ── Tool: log_transaction ──
server.tool(
  "log_transaction",
  "Log an income or expense transaction to Odoo and /Accounting/Current_Month.md",
  {
    description: z.string().describe("Transaction description"),
    amount: z.number().describe("Transaction amount"),
    type: z
      .enum(["income", "expense"])
      .describe("Transaction type: income or expense"),
    date: z
      .string()
      .optional()
      .describe("Transaction date (YYYY-MM-DD). Defaults to today."),
  },
  async ({ description, amount, type, date }) => {
    log("INFO", "log_transaction called", { description, amount, type });

    try {
      const result = await odoo.logTransaction(description, amount, type, date);

      const sign = type === "expense" ? "-" : "+";
      appendToCurrentMonth(
        `| ${result.date} | ${result.id} | ${description} | ${sign}$${amount.toFixed(2)} | ${type} |`
      );

      return {
        content: [
          {
            type: "text",
            text: [
              `✅ Transaction logged${result.simulated ? " (SIMULATED)" : ""}`,
              ``,
              `**ID:** ${result.id}`,
              `**Description:** ${description}`,
              `**Amount:** ${sign}$${amount.toFixed(2)}`,
              `**Type:** ${type}`,
              `**Date:** ${result.date}`,
            ].join("\n"),
          },
        ],
      };
    } catch (err) {
      log("ERROR", `log_transaction failed: ${err.message}`);
      return {
        content: [{ type: "text", text: `❌ Failed: ${err.message}` }],
      };
    }
  }
);

// ── Tool: get_invoices ──
server.tool(
  "get_invoices",
  "Get a summary of invoices from Odoo (filterable by status)",
  {
    status: z
      .enum(["draft", "posted", "cancel"])
      .optional()
      .default("draft")
      .describe("Filter by invoice status"),
    limit: z.number().optional().default(20).describe("Max invoices to return"),
  },
  async ({ status, limit }) => {
    log("INFO", "get_invoices called", { status, limit });

    try {
      const summary = await odoo.getInvoiceSummary(status, limit);

      const lines = [
        `# Invoice Summary${summary.simulated ? " (SIMULATED)" : ""}`,
        ``,
        `**Count:** ${summary.count} | **Total:** $${summary.total_amount.toFixed(2)}`,
        ``,
        `| Invoice | Partner | Amount | Status | Date | Ref |`,
        `|---------|---------|--------|--------|------|-----|`,
      ];

      summary.invoices.forEach((inv) => {
        lines.push(
          `| ${inv.name} | ${inv.partner} | $${inv.amount.toFixed(2)} | ${inv.status} | ${inv.date || "N/A"} | ${inv.ref || ""} |`
        );
      });

      return { content: [{ type: "text", text: lines.join("\n") }] };
    } catch (err) {
      return {
        content: [{ type: "text", text: `❌ Failed: ${err.message}` }],
      };
    }
  }
);

// ── Tool: get_balance ──
server.tool(
  "get_balance",
  "Get accounts receivable or payable balance from Odoo",
  {
    type: z
      .enum(["receivable", "payable"])
      .describe("Account type: receivable or payable"),
  },
  async ({ type }) => {
    log("INFO", "get_balance called", { type });

    try {
      const result = await odoo.getAccountBalance(type);

      return {
        content: [
          {
            type: "text",
            text: [
              `# ${type === "receivable" ? "Accounts Receivable" : "Accounts Payable"}${result.simulated ? " (SIMULATED)" : ""}`,
              ``,
              `**Balance:** $${result.balance.toFixed(2)}`,
              `**Currency:** ${result.currency}`,
              `**As of:** ${result.as_of}`,
            ].join("\n"),
          },
        ],
      };
    } catch (err) {
      return {
        content: [{ type: "text", text: `❌ Failed: ${err.message}` }],
      };
    }
  }
);

// ── Tool: read_accounting ──
server.tool(
  "read_accounting",
  "Read the /Accounting/Current_Month.md file for context on current financial state",
  {},
  async () => {
    log("INFO", "read_accounting called");

    if (!fs.existsSync(CURRENT_MONTH_FILE)) {
      return {
        content: [
          {
            type: "text",
            text: "⚠️ /Accounting/Current_Month.md not found. Run create_invoice or log_transaction to initialize.",
          },
        ],
      };
    }

    const content = fs.readFileSync(CURRENT_MONTH_FILE, "utf-8");
    return { content: [{ type: "text", text: content }] };
  }
);

// ── Tool: generate_audit ──
server.tool(
  "generate_audit",
  "Generate a weekly audit report based on Current_Month.md and Odoo data, and save to /Accounting/Audits/",
  {
    week_label: z
      .string()
      .optional()
      .describe("Label for the audit week (e.g. 'Week 3 Feb 2026')"),
  },
  async ({ week_label }) => {
    log("INFO", "generate_audit called", { week_label });

    const label = week_label || `Week of ${new Date().toISOString().split("T")[0]}`;

    // Gather data
    let monthData = "No data available.";
    if (fs.existsSync(CURRENT_MONTH_FILE)) {
      monthData = fs.readFileSync(CURRENT_MONTH_FILE, "utf-8");
    }

    let invoiceSummary, receivable, payable;
    try {
      invoiceSummary = await odoo.getInvoiceSummary("draft");
      receivable = await odoo.getAccountBalance("receivable");
      payable = await odoo.getAccountBalance("payable");
    } catch {
      invoiceSummary = { count: 0, total_amount: 0, invoices: [] };
      receivable = { balance: 0 };
      payable = { balance: 0 };
    }

    // Build audit report
    const auditContent = [
      `# Weekly Audit Report — ${label}`,
      ``,
      `**Generated:** ${new Date().toISOString()}`,
      `**Mode:** ${odoo.isSimulated ? "SIMULATED" : "LIVE"}`,
      ``,
      `## Financial Summary`,
      ``,
      `| Metric | Value |`,
      `|--------|-------|`,
      `| Draft Invoices | ${invoiceSummary.count} |`,
      `| Draft Total | $${invoiceSummary.total_amount.toFixed(2)} |`,
      `| Accounts Receivable | $${receivable.balance.toFixed(2)} |`,
      `| Accounts Payable | $${payable.balance.toFixed(2)} |`,
      `| Net Position | $${(receivable.balance - payable.balance).toFixed(2)} |`,
      ``,
      `## Current Month Activity`,
      ``,
      monthData,
      ``,
      `## Draft Invoices Pending Approval`,
      ``,
      `| Invoice | Partner | Amount | Ref |`,
      `|---------|---------|--------|-----|`,
      ...invoiceSummary.invoices.map(
        (inv) =>
          `| ${inv.name} | ${inv.partner} | $${inv.amount.toFixed(2)} | ${inv.ref || ""} |`
      ),
      ``,
      `## Audit Checklist`,
      ``,
      `- [ ] Review all draft invoices for accuracy`,
      `- [ ] Verify receivable/payable balances`,
      `- [ ] Confirm no payments > $500 were auto-approved`,
      `- [ ] Cross-check with bank statements`,
      `- [ ] Sign off on audit`,
      ``,
      `---`,
      `*Generated by AI Employee Odoo MCP Server*`,
    ].join("\n");

    // Save audit file
    const auditFilename = `audit_${new Date().toISOString().split("T")[0]}_${Date.now()}.md`;
    const auditPath = path.join(AUDIT_DIR, auditFilename);
    fs.writeFileSync(auditPath, auditContent, "utf-8");

    log("INFO", `Audit report saved: ${auditFilename}`);

    // Claude prompt for deeper analysis
    const claudePrompt = [
      `## Claude Audit Analysis Prompt`,
      ``,
      `Analyze the following weekly audit report for the AI Employee system.`,
      `Check for:`,
      `1. Any payments exceeding $500 that weren't flagged`,
      `2. Draft invoices older than 7 days that need attention`,
      `3. Discrepancies between receivable and payable balances`,
      `4. Unusual transaction patterns`,
      `5. Compliance with Company Handbook rules`,
      ``,
      `Provide actionable recommendations.`,
    ].join("\n");

    return {
      content: [
        {
          type: "text",
          text: [
            `✅ Audit report generated: ${auditFilename}`,
            ``,
            auditContent,
            ``,
            `---`,
            ``,
            claudePrompt,
          ].join("\n"),
        },
      ],
    };
  }
);

// ---------------------------------------------------------------------------
// Resource: Current Month Accounting
// ---------------------------------------------------------------------------
server.resource(
  "current-month",
  "vault://Accounting/Current_Month.md",
  async (uri) => {
    let content = "No accounting data yet.";
    if (fs.existsSync(CURRENT_MONTH_FILE)) {
      content = fs.readFileSync(CURRENT_MONTH_FILE, "utf-8");
    }
    return {
      contents: [{ uri: uri.href, text: content, mimeType: "text/markdown" }],
    };
  }
);

// ---------------------------------------------------------------------------
// Helper: Append to Current_Month.md
// ---------------------------------------------------------------------------
function appendToCurrentMonth(line) {
  if (!fs.existsSync(CURRENT_MONTH_FILE)) {
    const header = [
      `# Accounting — ${new Date().toLocaleString("default", { month: "long", year: "numeric" })}`,
      ``,
      `## Transactions`,
      ``,
      `| Date | ID | Description | Amount | Type |`,
      `|------|-----|-------------|--------|------|`,
    ].join("\n");
    fs.writeFileSync(CURRENT_MONTH_FILE, header + "\n", "utf-8");
  }
  fs.appendFileSync(CURRENT_MONTH_FILE, line + "\n", "utf-8");
  log("INFO", `Current_Month.md updated: ${line.substring(0, 80)}`);
}

// ---------------------------------------------------------------------------
// Start Server
// ---------------------------------------------------------------------------
async function main() {
  log("INFO", "Odoo MCP Server starting", {
    simulate: odoo.isSimulated,
    url: odoo.config.url,
  });

  const transport = new StdioServerTransport();
  await server.connect(transport);
  log("INFO", "Odoo MCP Server connected via stdio");
}

main().catch((err) => {
  log("ERROR", `Server failed: ${err.message}`);
  process.exit(1);
});
