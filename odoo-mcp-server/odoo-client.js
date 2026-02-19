/**
 * odoo-client.js — Odoo JSON-RPC Client with Retry Logic
 *
 * Connects to Odoo 19+ Community via JSON-RPC over HTTP.
 * All write operations are draft-only for safety.
 * Includes 3x retry with exponential backoff.
 *
 * Odoo JSON-RPC Endpoints:
 *   /jsonrpc          — general RPC
 *   /web/session/authenticate — authentication
 */

const http = require("http");
const https = require("https");
const fs = require("fs");
const path = require("path");

const LOG_FILE = path.join(__dirname, "odoo-mcp.log");

function log(level, msg, data = null) {
  const ts = new Date().toISOString();
  const entry = `[${ts}] [${level}] ${msg}${data ? " " + JSON.stringify(data) : ""}`;
  fs.appendFileSync(LOG_FILE, entry + "\n", "utf-8");
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------
const DEFAULT_CONFIG = {
  url: process.env.ODOO_URL || "http://localhost:8069",
  db: process.env.ODOO_DB || "odoo",
  username: process.env.ODOO_USER || "admin",
  password: process.env.ODOO_PASSWORD || "admin",
  simulate: process.env.ODOO_SIMULATE !== "false", // Default: simulate ON
};

const MAX_RETRIES = 3;
const RETRY_BASE_DELAY_MS = 1000;

// ---------------------------------------------------------------------------
// JSON-RPC Transport
// ---------------------------------------------------------------------------
async function jsonRpc(url, method, params, retries = MAX_RETRIES) {
  const payload = JSON.stringify({
    jsonrpc: "2.0",
    id: Date.now(),
    method: method,
    params: params,
  });

  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const result = await _httpPost(url, payload);
      if (result.error) {
        const errMsg =
          result.error.data?.message ||
          result.error.message ||
          JSON.stringify(result.error);
        throw new Error(`Odoo RPC Error: ${errMsg}`);
      }
      return result.result;
    } catch (err) {
      log("WARN", `RPC attempt ${attempt}/${retries} failed: ${err.message}`);
      if (attempt === retries) {
        log("ERROR", `RPC failed after ${retries} retries`, {
          method,
          error: err.message,
        });
        throw err;
      }
      const delay = RETRY_BASE_DELAY_MS * Math.pow(2, attempt - 1);
      await new Promise((r) => setTimeout(r, delay));
    }
  }
}

function _httpPost(urlStr, body) {
  return new Promise((resolve, reject) => {
    const parsedUrl = new URL(urlStr);
    const transport = parsedUrl.protocol === "https:" ? https : http;

    const options = {
      hostname: parsedUrl.hostname,
      port: parsedUrl.port || (parsedUrl.protocol === "https:" ? 443 : 80),
      path: parsedUrl.pathname,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(body),
      },
      timeout: 15000,
    };

    const req = transport.request(options, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        try {
          resolve(JSON.parse(data));
        } catch {
          reject(new Error(`Invalid JSON response: ${data.substring(0, 200)}`));
        }
      });
    });

    req.on("error", reject);
    req.on("timeout", () => {
      req.destroy();
      reject(new Error("Request timed out"));
    });

    req.write(body);
    req.end();
  });
}

// ---------------------------------------------------------------------------
// Odoo Client Class
// ---------------------------------------------------------------------------
class OdooClient {
  constructor(config = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.uid = null;
    this.sessionId = null;
    this._simInvoiceCounter = 1000;
    this._simTransactions = [];
  }

  get isSimulated() {
    return this.config.simulate;
  }

  // ── Authentication ──
  async authenticate() {
    if (this.isSimulated) {
      this.uid = 2; // Simulated admin UID
      log("INFO", "Simulated authentication successful", { uid: this.uid });
      return { uid: this.uid, simulated: true };
    }

    const result = await jsonRpc(
      `${this.config.url}/web/session/authenticate`,
      "call",
      {
        db: this.config.db,
        login: this.config.username,
        password: this.config.password,
      }
    );

    if (!result || !result.uid) {
      throw new Error("Authentication failed: invalid credentials");
    }

    this.uid = result.uid;
    this.sessionId = result.session_id;
    log("INFO", "Odoo authentication successful", {
      uid: this.uid,
      db: this.config.db,
    });
    return { uid: this.uid, db: this.config.db };
  }

  // ── Generic Model RPC ──
  async _call(model, method, args = [], kwargs = {}) {
    if (!this.uid) await this.authenticate();

    return jsonRpc(`${this.config.url}/jsonrpc`, "call", {
      service: "object",
      method: "execute_kw",
      args: [this.config.db, this.uid, this.config.password, model, method, args, kwargs],
    });
  }

  // ── Invoice Operations (Draft-Only) ──

  async createDraftInvoice(partnerName, lines, ref = "") {
    if (this.isSimulated) {
      return this._simCreateInvoice(partnerName, lines, ref);
    }

    // Find or create partner
    let partnerId = await this._findPartner(partnerName);
    if (!partnerId) {
      partnerId = await this._createPartner(partnerName);
    }

    // Build invoice lines
    const invoiceLines = lines.map((line) => [
      0,
      0,
      {
        name: line.description || "Item",
        quantity: line.quantity || 1,
        price_unit: line.price || 0,
        // account_id will use default from journal
      },
    ]);

    // Create draft invoice (move_type: 'out_invoice' = customer invoice)
    const invoiceId = await this._call("account.move", "create", [
      {
        move_type: "out_invoice",
        partner_id: partnerId,
        ref: ref || `AI-${Date.now()}`,
        invoice_line_ids: invoiceLines,
        // state will be 'draft' by default
      },
    ]);

    log("INFO", `Draft invoice created: ID=${invoiceId}`, {
      partner: partnerName,
      lines: lines.length,
    });

    return {
      id: invoiceId,
      partner: partnerName,
      status: "draft",
      lines: lines.length,
      total: lines.reduce((s, l) => s + (l.price || 0) * (l.quantity || 1), 0),
      ref: ref,
    };
  }

  async _findPartner(name) {
    const ids = await this._call("res.partner", "search", [
      [["name", "ilike", name]],
    ], { limit: 1 });
    return ids && ids.length > 0 ? ids[0] : null;
  }

  async _createPartner(name) {
    return this._call("res.partner", "create", [{ name, is_company: true }]);
  }

  _simCreateInvoice(partnerName, lines, ref) {
    this._simInvoiceCounter++;
    const invoiceId = this._simInvoiceCounter;
    const total = lines.reduce(
      (s, l) => s + (l.price || 0) * (l.quantity || 1),
      0
    );

    const invoice = {
      id: invoiceId,
      partner: partnerName,
      status: "draft",
      lines: lines.length,
      total,
      ref: ref || `SIM-${invoiceId}`,
      created: new Date().toISOString(),
      simulated: true,
    };

    log("INFO", `[SIM] Draft invoice created: ID=${invoiceId}`, invoice);
    return invoice;
  }

  // ── Transaction Logging ──

  async logTransaction(description, amount, type = "expense", date = null) {
    const txn = {
      description,
      amount,
      type, // 'income' or 'expense'
      date: date || new Date().toISOString().split("T")[0],
      logged_at: new Date().toISOString(),
    };

    if (this.isSimulated) {
      txn.id = `TXN-${Date.now()}`;
      txn.simulated = true;
      this._simTransactions.push(txn);
      log("INFO", `[SIM] Transaction logged: ${txn.id}`, txn);
      return txn;
    }

    // In production: create account.move.line or use account.analytic.line
    const moveId = await this._call("account.move", "create", [
      {
        move_type: "entry",
        ref: description,
        date: txn.date,
        line_ids: [
          [
            0,
            0,
            {
              name: description,
              debit: type === "expense" ? amount : 0,
              credit: type === "income" ? amount : 0,
            },
          ],
          [
            0,
            0,
            {
              name: description,
              debit: type === "income" ? amount : 0,
              credit: type === "expense" ? amount : 0,
            },
          ],
        ],
      },
    ]);

    txn.id = `MOVE-${moveId}`;
    log("INFO", `Transaction logged: ${txn.id}`, txn);
    return txn;
  }

  // ── Read Summaries ──

  async getInvoiceSummary(status = "draft", limit = 20) {
    if (this.isSimulated) {
      return this._simGetSummary();
    }

    const domain = [["move_type", "=", "out_invoice"]];
    if (status) domain.push(["state", "=", status]);

    const invoices = await this._call(
      "account.move",
      "search_read",
      [domain],
      {
        fields: [
          "name",
          "partner_id",
          "amount_total",
          "state",
          "invoice_date",
          "ref",
        ],
        limit,
        order: "create_date desc",
      }
    );

    const summary = {
      count: invoices.length,
      total_amount: invoices.reduce((s, inv) => s + (inv.amount_total || 0), 0),
      invoices: invoices.map((inv) => ({
        name: inv.name,
        partner: inv.partner_id ? inv.partner_id[1] : "Unknown",
        amount: inv.amount_total,
        status: inv.state,
        date: inv.invoice_date,
        ref: inv.ref,
      })),
    };

    log("INFO", `Invoice summary retrieved: ${summary.count} invoices`);
    return summary;
  }

  _simGetSummary() {
    return {
      count: 3,
      total_amount: 2450.0,
      simulated: true,
      invoices: [
        {
          name: "INV/2026/0001",
          partner: "Acme Corp",
          amount: 1200.0,
          status: "draft",
          date: "2026-02-15",
          ref: "Q1-Services",
        },
        {
          name: "INV/2026/0002",
          partner: "Vendor Supplies Co.",
          amount: 750.0,
          status: "draft",
          date: "2026-02-16",
          ref: "INV-4821",
        },
        {
          name: "INV/2026/0003",
          partner: "Coffee Shop",
          amount: 500.0,
          status: "draft",
          date: "2026-02-18",
          ref: "Team-Feb",
        },
      ],
    };
  }

  // ── Accounts Receivable / Payable ──

  async getAccountBalance(type = "receivable") {
    if (this.isSimulated) {
      return {
        type,
        balance: type === "receivable" ? 3200.0 : 1850.0,
        currency: "USD",
        as_of: new Date().toISOString().split("T")[0],
        simulated: true,
      };
    }

    const accountType =
      type === "receivable"
        ? "asset_receivable"
        : "liability_payable";

    const accounts = await this._call(
      "account.account",
      "search_read",
      [[["account_type", "=", accountType]]],
      { fields: ["name", "current_balance"], limit: 10 }
    );

    const total = accounts.reduce(
      (s, a) => s + Math.abs(a.current_balance || 0),
      0
    );

    return {
      type,
      balance: total,
      currency: "USD",
      accounts: accounts.map((a) => ({ name: a.name, balance: a.current_balance })),
      as_of: new Date().toISOString().split("T")[0],
    };
  }

  // ── Connection Test ──

  async testConnection() {
    if (this.isSimulated) {
      return {
        status: "ok",
        simulated: true,
        server: this.config.url,
        db: this.config.db,
        uid: 2,
      };
    }

    try {
      const auth = await this.authenticate();
      const version = await jsonRpc(`${this.config.url}/jsonrpc`, "call", {
        service: "common",
        method: "version",
        args: [],
      });
      return {
        status: "ok",
        server: this.config.url,
        db: this.config.db,
        uid: auth.uid,
        version: version?.server_version || "unknown",
      };
    } catch (err) {
      return {
        status: "error",
        server: this.config.url,
        error: err.message,
      };
    }
  }
}

module.exports = { OdooClient, DEFAULT_CONFIG };
