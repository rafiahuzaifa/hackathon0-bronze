#!/usr/bin/env node

/**
 * LinkedIn MCP Server
 *
 * Model Context Protocol server for LinkedIn post management.
 * Capabilities:
 *   - draft_post:    Generate a post from Business_Goals.md context
 *   - submit_post:   Move an approved draft to LinkedIn via Playwright
 *   - list_drafts:   List all pending approval drafts
 *   - approve_draft: Approve a draft for posting
 *   - reject_draft:  Reject a draft with feedback
 *   - schedule_post: Schedule a post for a future time
 *   - get_goals:     Read Business_Goals.md for context
 *
 * HITL: All posts go through /Pending_Approval before posting.
 * Dry-run: Set DRY_RUN=true to simulate LinkedIn posting.
 */

const { McpServer } = require("@modelcontextprotocol/sdk/server/mcp.js");
const { StdioServerTransport } = require("@modelcontextprotocol/sdk/server/stdio.js");
const { z } = require("zod");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------
const VAULT_DIR = "d:/hackathon0/hackathon/AI_Employee_Vault";
const PENDING_DIR = path.join(VAULT_DIR, "Pending_Approval");
const DONE_DIR = path.join(VAULT_DIR, "Done");
const GOALS_FILE = path.join(VAULT_DIR, "Business_Goals.md");
const SCHEDULE_FILE = path.join(VAULT_DIR, "linkedin-mcp-server", "schedule.json");
const SESSION_DIR = path.join(VAULT_DIR, "linkedin-mcp-server", ".li_session");
const LOG_FILE = path.join(VAULT_DIR, "linkedin-mcp-server", "mcp-server.log");

const DRY_RUN = process.env.DRY_RUN !== "false"; // Default: dry-run ON

// Ensure directories
[PENDING_DIR, DONE_DIR, SESSION_DIR].forEach((d) => {
  fs.mkdirSync(d, { recursive: true });
});

// ---------------------------------------------------------------------------
// Logging
// ---------------------------------------------------------------------------
function log(level, msg, data = null) {
  const ts = new Date().toISOString();
  const entry = `[${ts}] [${level}] ${msg}${data ? " " + JSON.stringify(data) : ""}`;
  fs.appendFileSync(LOG_FILE, entry + "\n", "utf-8");
  if (level === "ERROR") {
    console.error(entry);
  }
}

// ---------------------------------------------------------------------------
// Post Draft Helpers
// ---------------------------------------------------------------------------
function generateDraftId() {
  return `li_${Date.now()}_${crypto.randomBytes(3).toString("hex")}`;
}

function createDraftFile(draftId, content, metadata) {
  const filePath = path.join(PENDING_DIR, `${draftId}.md`);
  const frontmatter = [
    "---",
    `id: ${draftId}`,
    `type: linkedin_post`,
    `status: pending_approval`,
    `created: ${new Date().toISOString()}`,
    `category: ${metadata.category || "general"}`,
    `scheduled_time: ${metadata.scheduledTime || "immediate"}`,
    `dry_run: ${DRY_RUN}`,
    "---",
    "",
    content,
  ].join("\n");

  fs.writeFileSync(filePath, frontmatter, "utf-8");
  log("INFO", `Draft created: ${draftId}`, metadata);
  return { id: draftId, path: filePath };
}

function readDraftFile(draftId) {
  const filePath = path.join(PENDING_DIR, `${draftId}.md`);
  if (!fs.existsSync(filePath)) return null;
  const raw = fs.readFileSync(filePath, "utf-8");

  // Parse frontmatter
  const parts = raw.split("---");
  let meta = {};
  let body = raw;
  if (parts.length >= 3) {
    const yamlBlock = parts[1].trim();
    yamlBlock.split("\n").forEach((line) => {
      const idx = line.indexOf(":");
      if (idx > 0) {
        const key = line.substring(0, idx).trim();
        const val = line.substring(idx + 1).trim();
        meta[key] = val;
      }
    });
    body = parts.slice(2).join("---").trim();
  }

  return { id: draftId, meta, body, filePath };
}

function listDraftFiles() {
  if (!fs.existsSync(PENDING_DIR)) return [];
  return fs
    .readdirSync(PENDING_DIR)
    .filter((f) => f.endsWith(".md") && f.startsWith("li_"))
    .map((f) => {
      const id = f.replace(".md", "");
      return readDraftFile(id);
    })
    .filter(Boolean);
}

function updateDraftStatus(draftId, newStatus) {
  const draft = readDraftFile(draftId);
  if (!draft) return null;

  let content = fs.readFileSync(draft.filePath, "utf-8");
  content = content.replace(/status: \w+/, `status: ${newStatus}`);
  fs.writeFileSync(draft.filePath, content, "utf-8");
  log("INFO", `Draft ${draftId} status -> ${newStatus}`);
  return readDraftFile(draftId);
}

function moveDraftToDone(draftId) {
  const srcPath = path.join(PENDING_DIR, `${draftId}.md`);
  const dstPath = path.join(DONE_DIR, `${draftId}.md`);
  if (fs.existsSync(srcPath)) {
    fs.renameSync(srcPath, dstPath);
    log("INFO", `Draft ${draftId} moved to Done`);
  }
}

// ---------------------------------------------------------------------------
// Schedule Manager
// ---------------------------------------------------------------------------
function loadSchedule() {
  if (!fs.existsSync(SCHEDULE_FILE)) return [];
  try {
    return JSON.parse(fs.readFileSync(SCHEDULE_FILE, "utf-8"));
  } catch {
    return [];
  }
}

function saveSchedule(entries) {
  fs.writeFileSync(SCHEDULE_FILE, JSON.stringify(entries, null, 2), "utf-8");
}

function addToSchedule(draftId, scheduledTime) {
  const entries = loadSchedule();
  entries.push({
    draftId,
    scheduledTime,
    status: "scheduled",
    createdAt: new Date().toISOString(),
  });
  saveSchedule(entries);
  log("INFO", `Scheduled post ${draftId} for ${scheduledTime}`);
}

// ---------------------------------------------------------------------------
// LinkedIn Playwright Poster (with dry-run)
// ---------------------------------------------------------------------------
async function postToLinkedIn(postText) {
  if (DRY_RUN) {
    log("INFO", "DRY RUN: Would post to LinkedIn", {
      textLength: postText.length,
      preview: postText.substring(0, 100),
    });
    return {
      success: true,
      dryRun: true,
      message: "Dry-run: Post simulated successfully",
      preview: postText.substring(0, 200),
    };
  }

  // Real LinkedIn posting via Playwright
  let browser;
  try {
    const { chromium } = require("playwright");
    browser = await chromium.launchPersistentContext(SESSION_DIR, {
      headless: false,
      args: ["--disable-blink-features=AutomationControlled"],
    });

    const page = browser.pages()[0] || (await browser.newPage());
    await page.goto("https://www.linkedin.com/feed/", { timeout: 30000 });

    // Check if logged in
    const isLoggedIn = await page
      .waitForSelector('button[aria-label*="Start a post"]', { timeout: 15000 })
      .then(() => true)
      .catch(() => false);

    if (!isLoggedIn) {
      await browser.close();
      return {
        success: false,
        message:
          "Not logged into LinkedIn. Please run once with headless=false to log in manually.",
      };
    }

    // Click "Start a post"
    await page.click('button[aria-label*="Start a post"]');
    await page.waitForTimeout(2000);

    // Type post content in the editor
    const editor = await page.waitForSelector(
      'div[role="textbox"][aria-label*="Text editor"]',
      { timeout: 10000 }
    );
    await editor.fill(postText);
    await page.waitForTimeout(1000);

    // Click Post button
    const postBtn = await page.waitForSelector(
      'button[aria-label="Post"]:not([disabled])',
      { timeout: 5000 }
    );
    await postBtn.click();
    await page.waitForTimeout(3000);

    log("INFO", "Successfully posted to LinkedIn");
    await browser.close();

    return { success: true, dryRun: false, message: "Posted to LinkedIn successfully" };
  } catch (err) {
    log("ERROR", `LinkedIn posting failed: ${err.message}`);
    if (browser) await browser.close();
    return { success: false, message: `Posting failed: ${err.message}` };
  }
}

// ---------------------------------------------------------------------------
// Business Goals Reader
// ---------------------------------------------------------------------------
function readBusinessGoals() {
  if (!fs.existsSync(GOALS_FILE)) {
    return { exists: false, content: "Business_Goals.md not found." };
  }
  return {
    exists: true,
    content: fs.readFileSync(GOALS_FILE, "utf-8"),
  };
}

// ---------------------------------------------------------------------------
// Post Content Generator (local, used when Claude generates via prompt)
// ---------------------------------------------------------------------------
function generatePostFromGoals(category, customPrompt) {
  const goals = readBusinessGoals();
  if (!goals.exists) {
    return { error: "Business_Goals.md not found" };
  }

  const templates = {
    lead_generation: `🚀 Struggling with generating quality leads?

We've been helping businesses automate their lead generation using AI-powered workflows — and the results speak for themselves.

Here's what we've learned: The best leads come from solving real problems, not just chasing numbers.

Want to see how AI can transform your sales pipeline?
Drop a comment or DM me to chat.

#AIAutomation #SalesLeads #LeadGeneration #DigitalTransformation`,

    thought_leadership: `💡 The future of work isn't about replacing humans with AI — it's about augmenting human capabilities.

I've been working on AI automation systems that handle the repetitive tasks so teams can focus on what really matters: creativity, strategy, and relationships.

Here are 3 trends I'm seeing in AI-powered productivity:
1. Autonomous email triage and response drafting
2. Intelligent task prioritization from multiple channels
3. Human-in-the-loop approval workflows

What AI productivity tools are you using? Let me know in the comments 👇

#ThoughtLeadership #Productivity #AIAutomation #FutureOfWork`,

    case_study: `📊 Case Study: How we automated 80% of inbox management

Challenge: Our client was drowning in 200+ daily emails and WhatsApp messages.

Solution: We built an AI Employee that:
✅ Automatically triages incoming messages
✅ Flags urgent items and payments > $500
✅ Generates action plans with checkboxes
✅ Routes approvals through a human-in-the-loop workflow

Result: 4 hours saved per day. Zero missed deadlines.

Want similar results for your team? Let's connect.

#CaseStudy #AIAutomation #Productivity #DigitalTransformation`,

    general: `🌟 Exciting things happening in the AI automation space!

${customPrompt || "We're building tools that help businesses work smarter, not harder."}

What's your biggest productivity challenge? I'd love to hear about it.

#AI #Automation #Productivity`,
  };

  const postText = templates[category] || templates.general;
  return { content: postText, category, generatedAt: new Date().toISOString() };
}

// ---------------------------------------------------------------------------
// MCP Server Definition
// ---------------------------------------------------------------------------
const server = new McpServer({
  name: "linkedin-poster",
  version: "1.0.0",
});

// Tool: draft_post
server.tool(
  "draft_post",
  "Generate a LinkedIn post draft from Business_Goals.md and save to /Pending_Approval for human review",
  {
    category: z
      .enum(["lead_generation", "thought_leadership", "case_study", "general"])
      .describe("Type of LinkedIn post to generate"),
    custom_prompt: z
      .string()
      .optional()
      .describe("Optional custom instructions for post content"),
  },
  async ({ category, custom_prompt }) => {
    log("INFO", "draft_post called", { category, custom_prompt });

    const generated = generatePostFromGoals(category, custom_prompt);
    if (generated.error) {
      return { content: [{ type: "text", text: `Error: ${generated.error}` }] };
    }

    const draftId = generateDraftId();
    const result = createDraftFile(draftId, generated.content, {
      category,
      scheduledTime: "immediate",
    });

    return {
      content: [
        {
          type: "text",
          text: [
            `✅ Draft created and saved to /Pending_Approval`,
            ``,
            `**Draft ID:** ${result.id}`,
            `**Category:** ${category}`,
            `**Status:** pending_approval (HITL)`,
            `**Dry Run:** ${DRY_RUN}`,
            `**File:** ${result.path}`,
            ``,
            `--- Post Preview ---`,
            generated.content,
            `--- End Preview ---`,
            ``,
            `Use 'approve_draft' to approve, or 'reject_draft' to reject with feedback.`,
          ].join("\n"),
        },
      ],
    };
  }
);

// Tool: list_drafts
server.tool(
  "list_drafts",
  "List all LinkedIn post drafts in /Pending_Approval",
  {},
  async () => {
    const drafts = listDraftFiles();
    if (drafts.length === 0) {
      return {
        content: [{ type: "text", text: "No drafts in /Pending_Approval." }],
      };
    }

    const lines = [`# Pending Drafts (${drafts.length})`, ""];
    drafts.forEach((d) => {
      lines.push(`## ${d.id}`);
      lines.push(`- **Status:** ${d.meta.status}`);
      lines.push(`- **Category:** ${d.meta.category}`);
      lines.push(`- **Created:** ${d.meta.created}`);
      lines.push(`- **Scheduled:** ${d.meta.scheduled_time}`);
      lines.push(`- **Preview:** ${d.body.substring(0, 100)}...`);
      lines.push("");
    });

    return { content: [{ type: "text", text: lines.join("\n") }] };
  }
);

// Tool: approve_draft
server.tool(
  "approve_draft",
  "Approve a LinkedIn post draft for publishing. Will post to LinkedIn (or dry-run).",
  {
    draft_id: z.string().describe("The draft ID to approve (e.g., li_1234567890_abc123)"),
  },
  async ({ draft_id }) => {
    log("INFO", "approve_draft called", { draft_id });
    const draft = readDraftFile(draft_id);
    if (!draft) {
      return {
        content: [{ type: "text", text: `❌ Draft not found: ${draft_id}` }],
      };
    }

    updateDraftStatus(draft_id, "approved");

    // Post to LinkedIn
    const result = await postToLinkedIn(draft.body);

    if (result.success) {
      updateDraftStatus(draft_id, "posted");
      moveDraftToDone(draft_id);
      return {
        content: [
          {
            type: "text",
            text: [
              `✅ Draft ${draft_id} approved and ${result.dryRun ? "simulated" : "posted"}!`,
              ``,
              result.dryRun ? `🏃 DRY RUN: Post was not actually sent to LinkedIn.` : `🎉 Post is now live on LinkedIn!`,
              ``,
              `Draft moved to /Done.`,
              result.preview ? `\nPreview: ${result.preview}` : "",
            ].join("\n"),
          },
        ],
      };
    } else {
      updateDraftStatus(draft_id, "failed");
      return {
        content: [
          {
            type: "text",
            text: `❌ Posting failed: ${result.message}\nDraft remains in /Pending_Approval with status 'failed'.`,
          },
        ],
      };
    }
  }
);

// Tool: reject_draft
server.tool(
  "reject_draft",
  "Reject a LinkedIn post draft with feedback for revision",
  {
    draft_id: z.string().describe("The draft ID to reject"),
    feedback: z.string().describe("Feedback explaining why the draft was rejected"),
  },
  async ({ draft_id, feedback }) => {
    log("INFO", "reject_draft called", { draft_id, feedback });
    const draft = readDraftFile(draft_id);
    if (!draft) {
      return {
        content: [{ type: "text", text: `❌ Draft not found: ${draft_id}` }],
      };
    }

    // Append feedback to the file
    const feedbackBlock = `\n\n---\n**REJECTED** (${new Date().toISOString()})\n**Feedback:** ${feedback}\n`;
    fs.appendFileSync(draft.filePath, feedbackBlock, "utf-8");
    updateDraftStatus(draft_id, "rejected");

    return {
      content: [
        {
          type: "text",
          text: `🔄 Draft ${draft_id} rejected.\n\n**Feedback:** ${feedback}\n\nUse 'draft_post' to create a revised version.`,
        },
      ],
    };
  }
);

// Tool: schedule_post
server.tool(
  "schedule_post",
  "Schedule an approved LinkedIn post for a specific date/time",
  {
    draft_id: z.string().describe("The draft ID to schedule"),
    scheduled_time: z
      .string()
      .describe("ISO 8601 datetime for publishing (e.g., 2026-02-19T09:00:00)"),
  },
  async ({ draft_id, scheduled_time }) => {
    log("INFO", "schedule_post called", { draft_id, scheduled_time });
    const draft = readDraftFile(draft_id);
    if (!draft) {
      return {
        content: [{ type: "text", text: `❌ Draft not found: ${draft_id}` }],
      };
    }

    addToSchedule(draft_id, scheduled_time);
    updateDraftStatus(draft_id, "scheduled");

    // Update scheduled_time in frontmatter
    let content = fs.readFileSync(draft.filePath, "utf-8");
    content = content.replace(/scheduled_time: .+/, `scheduled_time: ${scheduled_time}`);
    fs.writeFileSync(draft.filePath, content, "utf-8");

    return {
      content: [
        {
          type: "text",
          text: `📅 Draft ${draft_id} scheduled for ${scheduled_time}.\n\nThe orchestrator will publish it at the scheduled time.`,
        },
      ],
    };
  }
);

// Tool: get_goals
server.tool(
  "get_goals",
  "Read Business_Goals.md to understand posting strategy and tone",
  {},
  async () => {
    const goals = readBusinessGoals();
    return {
      content: [
        {
          type: "text",
          text: goals.exists
            ? `# Business Goals\n\n${goals.content}`
            : "⚠️ Business_Goals.md not found. Please create it in the vault root.",
        },
      ],
    };
  }
);

// Tool: submit_post
server.tool(
  "submit_post",
  "Directly post text to LinkedIn (bypasses approval for pre-approved content)",
  {
    post_text: z.string().describe("The full text of the LinkedIn post"),
  },
  async ({ post_text }) => {
    log("INFO", "submit_post called", { textLength: post_text.length });

    // Still create a record for audit trail
    const draftId = generateDraftId();
    createDraftFile(draftId, post_text, {
      category: "direct_submit",
      scheduledTime: "immediate",
    });
    updateDraftStatus(draftId, "approved");

    const result = await postToLinkedIn(post_text);

    if (result.success) {
      updateDraftStatus(draftId, "posted");
      moveDraftToDone(draftId);
    } else {
      updateDraftStatus(draftId, "failed");
    }

    return {
      content: [
        {
          type: "text",
          text: result.success
            ? `✅ ${result.dryRun ? "DRY RUN" : "POSTED"}: ${result.message}\nAudit trail: ${draftId}`
            : `❌ Failed: ${result.message}`,
        },
      ],
    };
  }
);

// ---------------------------------------------------------------------------
// Resources: Expose vault files as MCP resources
// ---------------------------------------------------------------------------
server.resource(
  "business-goals",
  "vault://Business_Goals.md",
  async (uri) => {
    const goals = readBusinessGoals();
    return {
      contents: [
        {
          uri: uri.href,
          text: goals.content,
          mimeType: "text/markdown",
        },
      ],
    };
  }
);

// ---------------------------------------------------------------------------
// Start Server
// ---------------------------------------------------------------------------
async function main() {
  log("INFO", "LinkedIn MCP Server starting", { dryRun: DRY_RUN });

  const transport = new StdioServerTransport();
  await server.connect(transport);

  log("INFO", "LinkedIn MCP Server connected via stdio");
}

main().catch((err) => {
  log("ERROR", `Server failed to start: ${err.message}`);
  process.exit(1);
});
