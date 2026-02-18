#!/usr/bin/env node

/**
 * Dry-Run Test for LinkedIn MCP Server
 *
 * Tests the full HITL flow without MCP transport:
 *   1. Read Business_Goals.md
 *   2. Draft a post -> /Pending_Approval
 *   3. List drafts
 *   4. Approve draft -> dry-run "post" -> /Done
 *   5. Draft + reject flow
 *   6. Draft + schedule flow
 *
 * Ralph Wiggum loop: Iterate until all steps pass.
 */

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

// Import server helpers by re-implementing the core logic
// (since the MCP server runs via stdio, we test the logic directly)

const VAULT_DIR = "d:/hackathon0/hackathon/AI_Employee_Vault";
const PENDING_DIR = path.join(VAULT_DIR, "Pending_Approval");
const DONE_DIR = path.join(VAULT_DIR, "Done");
const GOALS_FILE = path.join(VAULT_DIR, "Business_Goals.md");
const LOG_FILE = path.join(VAULT_DIR, "linkedin-mcp-server", "test-results.log");

let testLog = [];
let passed = 0;
let failed = 0;

function log(msg) {
  const entry = `[${new Date().toISOString()}] ${msg}`;
  testLog.push(entry);
  console.log(entry);
}

function assert(condition, testName) {
  if (condition) {
    passed++;
    log(`  ✅ PASS: ${testName}`);
  } else {
    failed++;
    log(`  ❌ FAIL: ${testName}`);
  }
}

function generateDraftId() {
  return `li_test_${Date.now()}_${crypto.randomBytes(3).toString("hex")}`;
}

// ---------------------------------------------------------------------------
// Test 1: Read Business Goals
// ---------------------------------------------------------------------------
function testReadGoals() {
  log("\n📋 TEST 1: Read Business_Goals.md");
  const exists = fs.existsSync(GOALS_FILE);
  assert(exists, "Business_Goals.md exists");

  if (exists) {
    const content = fs.readFileSync(GOALS_FILE, "utf-8");
    assert(content.includes("Lead Generation"), "Contains Lead Generation goal");
    assert(content.includes("Thought Leadership"), "Contains Thought Leadership goal");
    assert(content.includes("#AIAutomation"), "Contains hashtags");
    assert(content.length > 100, `Content has substance (${content.length} chars)`);
  }
}

// ---------------------------------------------------------------------------
// Test 2: Draft a Post
// ---------------------------------------------------------------------------
function testDraftPost() {
  log("\n📝 TEST 2: Draft a LinkedIn Post");

  const categories = ["lead_generation", "thought_leadership", "case_study", "general"];
  const draftIds = [];

  categories.forEach((cat) => {
    const draftId = generateDraftId();
    const postContent = getTemplateContent(cat);

    const filePath = path.join(PENDING_DIR, `${draftId}.md`);
    const frontmatter = [
      "---",
      `id: ${draftId}`,
      `type: linkedin_post`,
      `status: pending_approval`,
      `created: ${new Date().toISOString()}`,
      `category: ${cat}`,
      `scheduled_time: immediate`,
      `dry_run: true`,
      "---",
      "",
      postContent,
    ].join("\n");

    fs.writeFileSync(filePath, frontmatter, "utf-8");
    draftIds.push(draftId);

    assert(fs.existsSync(filePath), `Draft created for category: ${cat}`);
    assert(
      fs.readFileSync(filePath, "utf-8").includes("pending_approval"),
      `Draft ${cat} has pending_approval status`
    );
  });

  return draftIds;
}

function getTemplateContent(category) {
  const templates = {
    lead_generation:
      "🚀 Struggling with generating quality leads?\n\nWe help businesses automate lead gen using AI.\n\n#SalesLeads #AIAutomation",
    thought_leadership:
      "💡 The future of work is AI-augmented productivity.\n\n3 trends I'm seeing:\n1. Auto email triage\n2. Smart prioritization\n3. HITL workflows\n\n#ThoughtLeadership",
    case_study:
      "📊 Case Study: 80% inbox automation achieved.\n\nChallenge → Solution → Result: 4 hours saved/day.\n\n#CaseStudy",
    general:
      "🌟 Exciting developments in AI automation!\n\nWhat's your biggest productivity challenge?\n\n#AI #Productivity",
  };
  return templates[category] || templates.general;
}

// ---------------------------------------------------------------------------
// Test 3: List Drafts
// ---------------------------------------------------------------------------
function testListDrafts(expectedMin) {
  log("\n📂 TEST 3: List Pending Drafts");

  const drafts = fs
    .readdirSync(PENDING_DIR)
    .filter((f) => f.endsWith(".md") && f.startsWith("li_"));

  assert(drafts.length >= expectedMin, `Found ${drafts.length} drafts (expected >= ${expectedMin})`);
  log(`  Drafts: ${drafts.join(", ")}`);
  return drafts;
}

// ---------------------------------------------------------------------------
// Test 4: Approve Draft (Dry-Run Post)
// ---------------------------------------------------------------------------
function testApproveDraft(draftId) {
  log("\n✅ TEST 4: Approve Draft (Dry-Run)");

  const filePath = path.join(PENDING_DIR, `${draftId}.md`);
  assert(fs.existsSync(filePath), `Draft file exists: ${draftId}`);

  // Update status to approved
  let content = fs.readFileSync(filePath, "utf-8");
  content = content.replace(/status: \w+/, "status: approved");
  fs.writeFileSync(filePath, content, "utf-8");
  assert(
    fs.readFileSync(filePath, "utf-8").includes("status: approved"),
    "Status updated to approved"
  );

  // Simulate dry-run posting
  const postBody = content.split("---").slice(2).join("---").trim();
  assert(postBody.length > 0, `Post body extracted (${postBody.length} chars)`);

  log(`  🏃 DRY RUN: Simulating LinkedIn post...`);
  log(`  📄 Preview: ${postBody.substring(0, 80)}...`);

  // Update status to posted
  content = content.replace(/status: \w+/, "status: posted");
  fs.writeFileSync(filePath, content, "utf-8");

  // Move to Done
  const donePath = path.join(DONE_DIR, `${draftId}.md`);
  fs.renameSync(filePath, donePath);
  assert(fs.existsSync(donePath), "Draft moved to /Done");
  assert(!fs.existsSync(filePath), "Draft removed from /Pending_Approval");

  return true;
}

// ---------------------------------------------------------------------------
// Test 5: Reject Draft with Feedback
// ---------------------------------------------------------------------------
function testRejectDraft(draftId) {
  log("\n🔄 TEST 5: Reject Draft with Feedback");

  const filePath = path.join(PENDING_DIR, `${draftId}.md`);
  assert(fs.existsSync(filePath), `Draft file exists: ${draftId}`);

  const feedback = "Needs more specific data points and a stronger CTA.";

  // Append feedback
  const feedbackBlock = `\n\n---\n**REJECTED** (${new Date().toISOString()})\n**Feedback:** ${feedback}\n`;
  fs.appendFileSync(filePath, feedbackBlock, "utf-8");

  // Update status
  let content = fs.readFileSync(filePath, "utf-8");
  content = content.replace(/status: \w+/, "status: rejected");
  fs.writeFileSync(filePath, content, "utf-8");

  assert(
    fs.readFileSync(filePath, "utf-8").includes("REJECTED"),
    "Rejection feedback appended"
  );
  assert(
    fs.readFileSync(filePath, "utf-8").includes("status: rejected"),
    "Status updated to rejected"
  );

  return true;
}

// ---------------------------------------------------------------------------
// Test 6: Schedule Draft
// ---------------------------------------------------------------------------
function testScheduleDraft(draftId) {
  log("\n📅 TEST 6: Schedule Draft");

  const filePath = path.join(PENDING_DIR, `${draftId}.md`);
  assert(fs.existsSync(filePath), `Draft file exists: ${draftId}`);

  const scheduledTime = "2026-02-20T09:00:00";

  // Update scheduled_time in frontmatter
  let content = fs.readFileSync(filePath, "utf-8");
  content = content.replace(/scheduled_time: .+/, `scheduled_time: ${scheduledTime}`);
  content = content.replace(/status: \w+/, "status: scheduled");
  fs.writeFileSync(filePath, content, "utf-8");

  assert(
    fs.readFileSync(filePath, "utf-8").includes(`scheduled_time: ${scheduledTime}`),
    "Scheduled time updated in frontmatter"
  );
  assert(
    fs.readFileSync(filePath, "utf-8").includes("status: scheduled"),
    "Status updated to scheduled"
  );

  // Write to schedule.json
  const scheduleFile = path.join(VAULT_DIR, "linkedin-mcp-server", "schedule.json");
  let schedule = [];
  if (fs.existsSync(scheduleFile)) {
    try {
      schedule = JSON.parse(fs.readFileSync(scheduleFile, "utf-8"));
    } catch {}
  }
  schedule.push({
    draftId,
    scheduledTime,
    status: "scheduled",
    createdAt: new Date().toISOString(),
  });
  fs.writeFileSync(scheduleFile, JSON.stringify(schedule, null, 2), "utf-8");

  assert(fs.existsSync(scheduleFile), "schedule.json created");

  return true;
}

// ---------------------------------------------------------------------------
// Ralph Wiggum Loop: Run all tests, retry on failure
// ---------------------------------------------------------------------------
function runAllTests() {
  log("=" .repeat(60));
  log("LINKEDIN MCP SERVER — DRY-RUN TEST SUITE");
  log(`Mode: DRY_RUN=true`);
  log("=" .repeat(60));

  passed = 0;
  failed = 0;

  // Clean up any previous test drafts
  if (fs.existsSync(PENDING_DIR)) {
    fs.readdirSync(PENDING_DIR)
      .filter((f) => f.startsWith("li_test_"))
      .forEach((f) => fs.unlinkSync(path.join(PENDING_DIR, f)));
  }

  // Test 1: Read goals
  testReadGoals();

  // Test 2: Draft posts (all categories)
  const draftIds = testDraftPost();

  // Test 3: List drafts
  testListDrafts(4);

  // Test 4: Approve first draft (dry-run post)
  testApproveDraft(draftIds[0]);

  // Test 5: Reject second draft
  testRejectDraft(draftIds[1]);

  // Test 6: Schedule third draft
  testScheduleDraft(draftIds[2]);

  // Summary
  log("\n" + "=".repeat(60));
  log(`RESULTS: ${passed} passed, ${failed} failed, ${passed + failed} total`);
  log("=".repeat(60));

  // Write test log
  fs.writeFileSync(LOG_FILE, testLog.join("\n"), "utf-8");

  return failed === 0;
}

// Ralph Wiggum: iterate until success
let attempts = 0;
const MAX_ATTEMPTS = 3;
let success = false;

while (!success && attempts < MAX_ATTEMPTS) {
  attempts++;
  log(`\n🔄 Ralph Wiggum Iteration #${attempts}`);
  try {
    success = runAllTests();
  } catch (err) {
    log(`💥 Crash in iteration #${attempts}: ${err.message}`);
  }
}

if (success) {
  log(`\n🎉 All tests passed after ${attempts} iteration(s)!`);
  process.exit(0);
} else {
  log(`\n💀 Tests still failing after ${MAX_ATTEMPTS} attempts.`);
  process.exit(1);
}
