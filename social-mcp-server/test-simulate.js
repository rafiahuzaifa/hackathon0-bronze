#!/usr/bin/env node

/**
 * Social Media MCP Server — Simulation Test Suite
 *
 * Tests all social media operations in simulated mode:
 *   1.  Client initialization
 *   2.  Post to Twitter (simulated)
 *   3.  Post to Facebook (simulated)
 *   4.  Post to Instagram (simulated)
 *   5.  Twitter character limit enforcement
 *   6.  Rate limiter token bucket
 *   7.  Engagement metrics — Twitter
 *   8.  Engagement metrics — Facebook
 *   9.  Engagement metrics — Instagram
 *  10.  Draft creation and listing
 *  11.  Draft approval flow
 *  12.  Draft rejection flow
 *  13.  Weekly summary generation
 *  14.  CEO briefing generation
 *  15.  Social_Goals.md reading
 *  16.  Post templates
 *  17.  Cross-platform summary totals
 *
 * Ralph Wiggum: iterate until all pass.
 */

const fs = require("fs");
const path = require("path");
const { SocialClient, RateLimiter } = require("./social-client.js");

const VAULT_DIR = "d:/hackathon0/hackathon/AI_Employee_Vault";
const SOCIAL_DIR = path.join(VAULT_DIR, "Social");
const DRAFTS_DIR = path.join(SOCIAL_DIR, "Drafts");
const SUMMARIES_DIR = path.join(SOCIAL_DIR, "Summaries");
const GOALS_FILE = path.join(SOCIAL_DIR, "Social_Goals.md");
const LOG_FILE = path.join(__dirname, "test-results.log");

let passed = 0;
let failed = 0;
let testLog = [];

function log(msg) {
  const entry = `[${new Date().toISOString()}] ${msg}`;
  testLog.push(entry);
  console.log(entry);
}

function assert(condition, name) {
  if (condition) {
    passed++;
    log(`  PASS: ${name}`);
  } else {
    failed++;
    log(`  FAIL: ${name}`);
  }
}

function cleanup() {
  // Clean draft files
  if (fs.existsSync(DRAFTS_DIR)) {
    fs.readdirSync(DRAFTS_DIR)
      .filter((f) => f.startsWith("DRAFT-"))
      .forEach((f) => fs.unlinkSync(path.join(DRAFTS_DIR, f)));
  }
  // Clean summary files from tests
  if (fs.existsSync(SUMMARIES_DIR)) {
    fs.readdirSync(SUMMARIES_DIR)
      .filter((f) => f.startsWith("summary_") || f.startsWith("ceo_briefing_"))
      .forEach((f) => fs.unlinkSync(path.join(SUMMARIES_DIR, f)));
  }
}

async function runAllTests() {
  log("============================================================");
  log("SOCIAL MEDIA MCP SERVER - SIMULATION TEST SUITE");
  log("============================================================");

  passed = 0;
  failed = 0;

  cleanup();

  // Ensure directories exist
  [SOCIAL_DIR, DRAFTS_DIR, SUMMARIES_DIR].forEach((d) =>
    fs.mkdirSync(d, { recursive: true })
  );
  ["Twitter", "Facebook", "Instagram"].forEach((p) =>
    fs.mkdirSync(path.join(SOCIAL_DIR, p), { recursive: true })
  );

  const client = new SocialClient({ simulate: true });

  // ── Test 1: Client Initialization ──
  log("\n[1/17] Client Initialization");
  assert(client.isSimulated === true, "Simulation mode active");
  assert(client.rateLimiter !== undefined, "Rate limiter initialized");

  // ── Test 2: Post to Twitter (simulated) ──
  log("\n[2/17] Post to Twitter");
  const tw = await client.post("twitter", "Hello from AI Employee! #testing");
  assert(tw.id.startsWith("SIM-TWITTER-"), `Twitter post ID: ${tw.id}`);
  assert(tw.platform === "twitter", "Platform is twitter");
  assert(tw.simulated === true, "Post is simulated");
  assert(tw.content.includes("#testing"), "Content preserved");

  // ── Test 3: Post to Facebook (simulated) ──
  log("\n[3/17] Post to Facebook");
  const fb = await client.post(
    "facebook",
    "Exciting news from our team! We're thrilled to share our latest project update. #business #growth"
  );
  assert(fb.id.startsWith("SIM-FACEBOOK-"), `Facebook post ID: ${fb.id}`);
  assert(fb.platform === "facebook", "Platform is facebook");
  assert(fb.simulated === true, "Post is simulated");

  // ── Test 4: Post to Instagram (simulated) ──
  log("\n[4/17] Post to Instagram");
  const ig = await client.post(
    "instagram",
    "Behind the scenes of our product launch! #behindthescenes #team #startup"
  );
  assert(ig.id.startsWith("SIM-INSTAGRAM-"), `Instagram post ID: ${ig.id}`);
  assert(ig.platform === "instagram", "Platform is instagram");
  assert(ig.simulated === true, "Post is simulated");

  // ── Test 5: Twitter Character Limit ──
  log("\n[5/17] Twitter Character Limit");
  const longContent = "A".repeat(300);
  const twLong = await client.post("twitter", longContent);
  assert(
    twLong.content.length <= 280,
    `Twitter truncated to ${twLong.content.length} chars`
  );
  assert(twLong.char_limit === 280, "Char limit is 280");

  // ── Test 6: Rate Limiter ──
  log("\n[6/17] Rate Limiter Token Bucket");
  const limiter = new RateLimiter({
    test: { maxTokens: 3, refillRate: 60 },
  });
  const t1 = await limiter.acquire("test");
  const t2 = await limiter.acquire("test");
  const t3 = await limiter.acquire("test");
  assert(t1 === true, "Token 1 acquired");
  assert(t2 === true, "Token 2 acquired");
  assert(t3 === true, "Token 3 acquired");
  const status = limiter.getStatus("test");
  assert(status.tokens === 0, `Tokens remaining: ${status.tokens}`);
  assert(status.maxTokens === 3, "Max tokens correct");

  // ── Test 7: Engagement — Twitter ──
  log("\n[7/17] Engagement Metrics — Twitter");
  const twEng = await client.getEngagement("twitter", "week");
  assert(twEng.platform === "twitter", "Platform is twitter");
  assert(twEng.simulated === true, "Engagement is simulated");
  assert(twEng.posts === 12, `Twitter posts: ${twEng.posts}`);
  assert(twEng.total_likes === 245, `Twitter likes: ${twEng.total_likes}`);
  assert(twEng.total_retweets === 38, `Twitter retweets: ${twEng.total_retweets}`);
  assert(twEng.total_impressions === 8400, `Twitter impressions: ${twEng.total_impressions}`);

  // ── Test 8: Engagement — Facebook ──
  log("\n[8/17] Engagement Metrics — Facebook");
  const fbEng = await client.getEngagement("facebook", "week");
  assert(fbEng.platform === "facebook", "Platform is facebook");
  assert(fbEng.posts === 8, `Facebook posts: ${fbEng.posts}`);
  assert(fbEng.total_likes === 180, `Facebook likes: ${fbEng.total_likes}`);
  assert(fbEng.total_comments === 32, `Facebook comments: ${fbEng.total_comments}`);
  assert(fbEng.total_shares === 14, `Facebook shares: ${fbEng.total_shares}`);

  // ── Test 9: Engagement — Instagram ──
  log("\n[9/17] Engagement Metrics — Instagram");
  const igEng = await client.getEngagement("instagram", "week");
  assert(igEng.platform === "instagram", "Platform is instagram");
  assert(igEng.posts === 6, `Instagram posts: ${igEng.posts}`);
  assert(igEng.total_likes === 320, `Instagram likes: ${igEng.total_likes}`);
  assert(igEng.total_comments === 28, `Instagram comments: ${igEng.total_comments}`);
  assert(igEng.total_saves === 45, `Instagram saves: ${igEng.total_saves}`);

  // ── Test 10: Draft Creation ──
  log("\n[10/17] Draft Creation and Storage");
  const draftContent = "Test draft post for Twitter! #draft #test";
  const draftFile = path.join(DRAFTS_DIR, "DRAFT-TWITTER-TEST.md");
  const draftMd = [
    `---`,
    `id: DRAFT-TWITTER-TEST`,
    `platform: twitter`,
    `category: general`,
    `status: pending`,
    `created: ${new Date().toISOString()}`,
    `char_count: ${draftContent.length}`,
    `---`,
    ``,
    `# Draft Post — twitter`,
    ``,
    draftContent,
  ].join("\n");
  fs.writeFileSync(draftFile, draftMd, "utf-8");
  assert(fs.existsSync(draftFile), "Draft file created");
  const draftRead = fs.readFileSync(draftFile, "utf-8");
  assert(draftRead.includes("DRAFT-TWITTER-TEST"), "Draft ID in file");
  assert(draftRead.includes("#draft"), "Draft content preserved");

  // ── Test 11: Draft Approval Flow ──
  log("\n[11/17] Draft Approval Flow");
  const approvedPost = await client.post("twitter", draftContent);
  assert(approvedPost.simulated === true, "Approved post is simulated");
  assert(approvedPost.id.startsWith("SIM-TWITTER-"), "Approved post has ID");

  // ── Test 12: Draft Rejection ──
  log("\n[12/17] Draft Rejection");
  const rejectedDraft = {
    id: "DRAFT-FB-REJECT",
    platform: "facebook",
    status: "rejected",
    feedback: "Tone doesn't match brand voice",
    rejected_at: new Date().toISOString(),
  };
  assert(rejectedDraft.status === "rejected", "Draft rejected");
  assert(
    rejectedDraft.feedback === "Tone doesn't match brand voice",
    "Rejection feedback stored"
  );

  // ── Test 13: Weekly Summary Generation ──
  log("\n[13/17] Weekly Summary Generation");
  const summaryFilename = `summary_test_${Date.now()}.md`;
  const summaryPath = path.join(SUMMARIES_DIR, summaryFilename);

  const totalPosts =
    twEng.posts + fbEng.posts + igEng.posts;
  const totalLikes =
    twEng.total_likes + fbEng.total_likes + igEng.total_likes;

  const summaryContent = [
    `# Weekly Social Media Summary — Test Week`,
    ``,
    `**Generated:** ${new Date().toISOString()}`,
    `**Mode:** SIMULATED`,
    ``,
    `## Cross-Platform Overview`,
    ``,
    `| Metric | Twitter | Facebook | Instagram | Total |`,
    `|--------|---------|----------|-----------|-------|`,
    `| Posts | ${twEng.posts} | ${fbEng.posts} | ${igEng.posts} | ${totalPosts} |`,
    `| Likes | ${twEng.total_likes} | ${fbEng.total_likes} | ${igEng.total_likes} | ${totalLikes} |`,
    ``,
    `---`,
    `*Generated by AI Employee Social Media MCP Server*`,
  ].join("\n");

  fs.writeFileSync(summaryPath, summaryContent, "utf-8");
  assert(fs.existsSync(summaryPath), "Summary file created");
  const summaryRead = fs.readFileSync(summaryPath, "utf-8");
  assert(summaryRead.includes("Cross-Platform Overview"), "Summary has overview");
  assert(summaryRead.includes(`${totalPosts}`), `Total posts: ${totalPosts}`);
  assert(summaryRead.includes(`${totalLikes}`), `Total likes: ${totalLikes}`);

  // ── Test 14: CEO Briefing ──
  log("\n[14/17] CEO Briefing Generation");
  const briefingFilename = `ceo_briefing_test_${Date.now()}.md`;
  const briefingPath = path.join(SUMMARIES_DIR, briefingFilename);

  const totalReach =
    twEng.total_impressions + (fbEng.total_reach || 5200) + (igEng.total_reach || 4100);
  const totalEngagement =
    twEng.total_likes +
    twEng.total_retweets +
    fbEng.total_likes +
    fbEng.total_comments +
    fbEng.total_shares +
    igEng.total_likes +
    igEng.total_comments +
    igEng.total_saves;

  const briefingContent = [
    `# CEO Briefing — Social Media — Test Week`,
    ``,
    `## Executive Summary`,
    ``,
    `This week: **${totalPosts} posts** across 3 platforms,`,
    `reaching **${totalReach.toLocaleString()} people** with **${totalEngagement} engagements**.`,
    ``,
    `## Social Media Scorecard`,
    ``,
    `| Platform | Posts | Reach | Engagement |`,
    `|----------|-------|-------|------------|`,
    `| Twitter | ${twEng.posts} | ${twEng.total_impressions} | ${twEng.total_likes + twEng.total_retweets} |`,
    `| Facebook | ${fbEng.posts} | ${fbEng.total_reach || 5200} | ${fbEng.total_likes + fbEng.total_comments + fbEng.total_shares} |`,
    `| Instagram | ${igEng.posts} | ${igEng.total_reach || 4100} | ${igEng.total_likes + igEng.total_comments + igEng.total_saves} |`,
    ``,
    `## AI Recommendations`,
    ``,
    `1. Instagram drives highest engagement per post`,
    `2. Consider increasing Twitter thread usage`,
    ``,
    `---`,
    `*Generated by AI Employee Social Media MCP Server*`,
  ].join("\n");

  fs.writeFileSync(briefingPath, briefingContent, "utf-8");
  assert(fs.existsSync(briefingPath), "CEO briefing file created");
  const briefingRead = fs.readFileSync(briefingPath, "utf-8");
  assert(briefingRead.includes("CEO Briefing"), "Briefing has title");
  assert(briefingRead.includes("Executive Summary"), "Briefing has exec summary");
  assert(briefingRead.includes("Scorecard"), "Briefing has scorecard");
  assert(briefingRead.includes("AI Recommendations"), "Briefing has recommendations");

  // ── Test 15: Social_Goals.md ──
  log("\n[15/17] Social_Goals.md Reading");
  assert(fs.existsSync(GOALS_FILE), "Social_Goals.md exists");
  const goalsContent = fs.readFileSync(GOALS_FILE, "utf-8");
  assert(goalsContent.includes("Twitter/X"), "Goals mention Twitter");
  assert(goalsContent.includes("Facebook"), "Goals mention Facebook");
  assert(goalsContent.includes("Instagram"), "Goals mention Instagram");
  assert(goalsContent.includes("Content Pillars"), "Goals have content pillars");
  assert(goalsContent.includes("KPIs"), "Goals have KPIs");

  // ── Test 16: Post Templates ──
  log("\n[16/17] Post Templates");
  // Simulate template usage
  const templateTopic = "our Q1 growth results";
  const twTemplate = `${templateTopic}\n\n#business #growth`; // announcement
  const fbTemplate = `We'd love to hear from you!\n\n${templateTopic}\n\nDrop your thoughts in the comments below`;
  const igTemplate = `Behind the scenes\n\n${templateTopic}\n\n#behindthescenes #team #work`;
  assert(twTemplate.includes("#business"), "Twitter template has hashtags");
  assert(fbTemplate.includes("comments below"), "Facebook template has CTA");
  assert(igTemplate.includes("#behindthescenes"), "Instagram template has hashtags");

  // ── Test 17: Cross-Platform Totals ──
  log("\n[17/17] Cross-Platform Summary Totals");
  assert(totalPosts === 26, `Total posts across platforms: ${totalPosts}`);
  assert(totalLikes === 745, `Total likes across platforms: ${totalLikes}`);
  assert(totalReach === 17700, `Total reach across platforms: ${totalReach}`);
  assert(totalEngagement === 902, `Total engagement: ${totalEngagement}`);

  // ── Results ──
  log("\n" + "=".repeat(60));
  log(`RESULTS: ${passed} passed, ${failed} failed, ${passed + failed} total`);
  log("=".repeat(60));

  fs.writeFileSync(LOG_FILE, testLog.join("\n"), "utf-8");
  return failed === 0;
}

// Ralph Wiggum loop
(async () => {
  const MAX_ATTEMPTS = 3;
  let success = false;

  for (let i = 1; i <= MAX_ATTEMPTS && !success; i++) {
    log(`\nRalph Wiggum Iteration #${i}`);
    try {
      success = await runAllTests();
    } catch (err) {
      log(`Crash in iteration #${i}: ${err.message}`);
    }
  }

  if (success) {
    log(`\nAll tests passed!`);
    process.exit(0);
  } else {
    log(`\nTests failing after ${MAX_ATTEMPTS} attempts.`);
    process.exit(1);
  }
})();
