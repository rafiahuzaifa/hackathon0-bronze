#!/usr/bin/env node

/**
 * Social Media MCP Server — Twitter/X, Facebook, Instagram
 *
 * Unified MCP server for all social media platforms.
 * Claude analyzes /Social/ folder, drafts posts from goals, requires HITL approval.
 *
 * Tools:
 *   1. draft_post         — Draft a post for any platform
 *   2. list_drafts        — List all pending drafts
 *   3. approve_post       — Approve a draft for posting
 *   4. reject_post        — Reject a draft with feedback
 *   5. submit_post        — Actually post to platform (dry-run by default)
 *   6. get_engagement     — Get engagement metrics per platform
 *   7. get_rate_limits    — Check rate limit status
 *   8. generate_summary   — Generate weekly social media summary
 *   9. generate_ceo_briefing — Generate CEO briefing with social metrics
 *  10. get_social_goals   — Read Social_Goals.md
 *
 * Resources:
 *   - vault://Social/Social_Goals.md
 */

const { McpServer } = require("@modelcontextprotocol/sdk/server/mcp.js");
const {
  StdioServerTransport,
} = require("@modelcontextprotocol/sdk/server/stdio.js");
const { z } = require("zod");
const fs = require("fs");
const path = require("path");
const { SocialClient } = require("./social-client.js");

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------
const VAULT_DIR = "d:/hackathon0/hackathon/AI_Employee_Vault";
const SOCIAL_DIR = path.join(VAULT_DIR, "Social");
const DRAFTS_DIR = path.join(SOCIAL_DIR, "Drafts");
const SUMMARIES_DIR = path.join(SOCIAL_DIR, "Summaries");
const GOALS_FILE = path.join(SOCIAL_DIR, "Social_Goals.md");
const PENDING_DIR = path.join(VAULT_DIR, "Pending_Approval");
const LOG_FILE = path.join(__dirname, "social-mcp.log");

const DRY_RUN = process.env.DRY_RUN !== "false";

[SOCIAL_DIR, DRAFTS_DIR, SUMMARIES_DIR, PENDING_DIR].forEach((d) =>
  fs.mkdirSync(d, { recursive: true })
);
["Twitter", "Facebook", "Instagram"].forEach((p) =>
  fs.mkdirSync(path.join(SOCIAL_DIR, p), { recursive: true })
);

function log(level, msg, data = null) {
  const ts = new Date().toISOString();
  const entry = `[${ts}] [${level}] ${msg}${data ? " " + JSON.stringify(data) : ""}`;
  fs.appendFileSync(LOG_FILE, entry + "\n", "utf-8");
}

// ---------------------------------------------------------------------------
// Social Client + Draft Store
// ---------------------------------------------------------------------------
const social = new SocialClient();
const drafts = new Map(); // id -> draft object
let draftCounter = 0;

const PLATFORMS = ["twitter", "facebook", "instagram"];

// Platform character limits
const CHAR_LIMITS = { twitter: 280, facebook: 63206, instagram: 2200 };

// Post templates
const POST_TEMPLATES = {
  twitter: {
    announcement: (topic) =>
      `${topic}\n\n#business #growth`,
    engagement: (topic) =>
      `What's your take on ${topic}? Let us know! 👇\n\n#discussion`,
    thought_leadership: (topic) =>
      `Key insight: ${topic}\n\nThread 🧵`,
  },
  facebook: {
    announcement: (topic) =>
      `📢 ${topic}\n\nWe're excited to share this update with our community. What do you think?\n\n#business #update`,
    engagement: (topic) =>
      `We'd love to hear from you!\n\n${topic}\n\nDrop your thoughts in the comments below 👇`,
    case_study: (topic) =>
      `📊 Success Story\n\n${topic}\n\nRead more about how we achieved these results.\n\n#casestudy #results`,
  },
  instagram: {
    announcement: (topic) =>
      `${topic}\n\n✨ Double-tap if you agree!\n\n#business #entrepreneur #growth #success`,
    behind_scenes: (topic) =>
      `Behind the scenes 🎬\n\n${topic}\n\n#behindthescenes #team #work`,
    motivation: (topic) =>
      `💡 ${topic}\n\nTag someone who needs to see this!\n\n#motivation #business #hustle`,
  },
};

// ---------------------------------------------------------------------------
// MCP Server
// ---------------------------------------------------------------------------
const server = new McpServer({
  name: "social-media",
  version: "1.0.0",
});

// ── Tool 1: draft_post ──
server.tool(
  "draft_post",
  "Draft a social media post for Twitter/X, Facebook, or Instagram. Saved to /Social/Drafts/ for approval.",
  {
    platform: z
      .enum(["twitter", "facebook", "instagram"])
      .describe("Target platform"),
    content: z.string().describe("Post content/text"),
    category: z
      .enum([
        "announcement",
        "engagement",
        "thought_leadership",
        "case_study",
        "behind_scenes",
        "motivation",
        "general",
      ])
      .optional()
      .default("general")
      .describe("Post category"),
    use_template: z
      .boolean()
      .optional()
      .default(false)
      .describe("Use platform template to wrap content"),
    image_url: z
      .string()
      .optional()
      .describe("Image URL (required for Instagram feed posts)"),
  },
  async ({ platform, content, category, use_template, image_url }) => {
    log("INFO", "draft_post called", { platform, category });

    const charLimit = CHAR_LIMITS[platform];
    let finalContent = content;

    // Apply template if requested
    if (use_template && POST_TEMPLATES[platform]?.[category]) {
      finalContent = POST_TEMPLATES[platform][category](content);
    }

    // Enforce character limit
    if (finalContent.length > charLimit) {
      finalContent = finalContent.substring(0, charLimit - 3) + "...";
    }

    draftCounter++;
    const draftId = `DRAFT-${platform.toUpperCase()}-${draftCounter}`;
    const draft = {
      id: draftId,
      platform,
      content: finalContent,
      category,
      image_url: image_url || null,
      char_count: finalContent.length,
      char_limit: charLimit,
      status: "pending",
      created: new Date().toISOString(),
      hashtags: (finalContent.match(/#\w+/g) || []),
    };

    drafts.set(draftId, draft);

    // Save to /Social/Drafts/
    const draftFile = path.join(DRAFTS_DIR, `${draftId}.md`);
    const draftMd = [
      `---`,
      `id: ${draftId}`,
      `platform: ${platform}`,
      `category: ${category}`,
      `status: pending`,
      `created: ${draft.created}`,
      `char_count: ${draft.char_count}`,
      `---`,
      ``,
      `# Draft Post — ${platform}`,
      ``,
      finalContent,
      ``,
      `---`,
      `*Hashtags: ${draft.hashtags.join(", ") || "none"}*`,
      `*Characters: ${draft.char_count}/${charLimit}*`,
    ].join("\n");
    fs.writeFileSync(draftFile, draftMd, "utf-8");

    // Also write to /Pending_Approval/
    const approvalFile = path.join(PENDING_DIR, `social_${draftId}.md`);
    const approvalMd = [
      `---`,
      `action: social_post`,
      `platform: ${platform}`,
      `draft_id: ${draftId}`,
      `status: pending`,
      `created: ${draft.created}`,
      `expires: ${new Date(Date.now() + 24 * 3600 * 1000).toISOString()}`,
      `---`,
      ``,
      `# Social Media Post Approval — ${platform}`,
      ``,
      `**Platform:** ${platform}`,
      `**Category:** ${category}`,
      `**Characters:** ${draft.char_count}/${charLimit}`,
      ``,
      `## Content`,
      ``,
      finalContent,
      ``,
      `---`,
      `Move to /Approved to post, or /Rejected to discard.`,
    ].join("\n");
    fs.writeFileSync(approvalFile, approvalMd, "utf-8");

    return {
      content: [
        {
          type: "text",
          text: [
            `Draft created: ${draftId}`,
            ``,
            `**Platform:** ${platform}`,
            `**Category:** ${category}`,
            `**Characters:** ${draft.char_count}/${charLimit}`,
            `**Hashtags:** ${draft.hashtags.join(", ") || "none"}`,
            ``,
            `\`\`\``,
            finalContent,
            `\`\`\``,
            ``,
            `Saved to /Social/Drafts/ and /Pending_Approval/`,
            `Approve with approve_post or reject with reject_post.`,
          ].join("\n"),
        },
      ],
    };
  }
);

// ── Tool 2: list_drafts ──
server.tool(
  "list_drafts",
  "List all pending social media drafts",
  {
    platform: z
      .enum(["twitter", "facebook", "instagram", "all"])
      .optional()
      .default("all")
      .describe("Filter by platform"),
  },
  async ({ platform }) => {
    log("INFO", "list_drafts called", { platform });

    const allDrafts = Array.from(drafts.values()).filter(
      (d) =>
        d.status === "pending" &&
        (platform === "all" || d.platform === platform)
    );

    if (allDrafts.length === 0) {
      return {
        content: [{ type: "text", text: "No pending drafts." }],
      };
    }

    const lines = [
      `# Pending Drafts (${allDrafts.length})`,
      ``,
      `| ID | Platform | Category | Chars | Created |`,
      `|----|----------|----------|-------|---------|`,
    ];

    allDrafts.forEach((d) => {
      lines.push(
        `| ${d.id} | ${d.platform} | ${d.category} | ${d.char_count}/${d.char_limit} | ${d.created.split("T")[0]} |`
      );
    });

    return { content: [{ type: "text", text: lines.join("\n") }] };
  }
);

// ── Tool 3: approve_post ──
server.tool(
  "approve_post",
  "Approve a draft post for publishing. In DRY_RUN mode, simulates posting.",
  {
    draft_id: z.string().describe("Draft ID to approve"),
  },
  async ({ draft_id }) => {
    log("INFO", "approve_post called", { draft_id });

    const draft = drafts.get(draft_id);
    if (!draft) {
      return {
        content: [{ type: "text", text: `Draft not found: ${draft_id}` }],
      };
    }
    if (draft.status !== "pending") {
      return {
        content: [
          {
            type: "text",
            text: `Draft ${draft_id} is already ${draft.status}`,
          },
        ],
      };
    }

    draft.status = "approved";
    draft.approved_at = new Date().toISOString();

    // Post if not dry-run
    let postResult = null;
    if (!DRY_RUN) {
      try {
        postResult = await social.post(draft.platform, draft.content, {
          image_url: draft.image_url,
        });
        draft.status = "posted";
        draft.post_id = postResult.id;
        draft.posted_at = postResult.posted_at;
      } catch (err) {
        draft.status = "failed";
        draft.error = err.message;
      }
    } else {
      // Dry-run simulation
      postResult = await social.post(draft.platform, draft.content, {
        image_url: draft.image_url,
      });
      draft.status = "posted_simulated";
      draft.post_id = postResult.id;
      draft.posted_at = postResult.posted_at;
    }

    // Save posted record to platform folder
    const platformDir = path.join(SOCIAL_DIR, capitalize(draft.platform));
    const postFile = path.join(
      platformDir,
      `post_${draft.id}_${Date.now()}.md`
    );
    const postMd = [
      `---`,
      `id: ${draft.post_id || draft.id}`,
      `platform: ${draft.platform}`,
      `status: ${draft.status}`,
      `posted_at: ${draft.posted_at || "N/A"}`,
      `---`,
      ``,
      draft.content,
    ].join("\n");
    fs.writeFileSync(postFile, postMd, "utf-8");

    // Remove from Pending_Approval
    const approvalFile = path.join(PENDING_DIR, `social_${draft_id}.md`);
    if (fs.existsSync(approvalFile)) fs.unlinkSync(approvalFile);

    return {
      content: [
        {
          type: "text",
          text: [
            `Post ${draft.status === "posted_simulated" ? "approved (DRY RUN)" : draft.status}`,
            ``,
            `**Draft:** ${draft_id}`,
            `**Platform:** ${draft.platform}`,
            `**Post ID:** ${draft.post_id || "N/A"}`,
            postResult?.simulated ? `**Mode:** SIMULATED` : "",
            draft.error ? `**Error:** ${draft.error}` : "",
          ]
            .filter(Boolean)
            .join("\n"),
        },
      ],
    };
  }
);

// ── Tool 4: reject_post ──
server.tool(
  "reject_post",
  "Reject a draft post with optional feedback",
  {
    draft_id: z.string().describe("Draft ID to reject"),
    feedback: z
      .string()
      .optional()
      .default("")
      .describe("Reason for rejection"),
  },
  async ({ draft_id, feedback }) => {
    log("INFO", "reject_post called", { draft_id, feedback });

    const draft = drafts.get(draft_id);
    if (!draft) {
      return {
        content: [{ type: "text", text: `Draft not found: ${draft_id}` }],
      };
    }

    draft.status = "rejected";
    draft.rejected_at = new Date().toISOString();
    draft.feedback = feedback;

    // Remove from Pending_Approval
    const approvalFile = path.join(PENDING_DIR, `social_${draft_id}.md`);
    if (fs.existsSync(approvalFile)) fs.unlinkSync(approvalFile);

    return {
      content: [
        {
          type: "text",
          text: `Draft ${draft_id} rejected.${feedback ? `\nFeedback: ${feedback}` : ""}`,
        },
      ],
    };
  }
);

// ── Tool 5: submit_post ──
server.tool(
  "submit_post",
  "Directly post content to a platform (bypasses draft flow). Use approve_post for HITL workflow.",
  {
    platform: z
      .enum(["twitter", "facebook", "instagram"])
      .describe("Target platform"),
    content: z.string().describe("Post content"),
    image_url: z
      .string()
      .optional()
      .describe("Image URL for Instagram"),
  },
  async ({ platform, content, image_url }) => {
    log("INFO", "submit_post called", { platform });

    try {
      const result = await social.post(platform, content, { image_url });

      // Save to platform folder
      const platformDir = path.join(SOCIAL_DIR, capitalize(platform));
      const postFile = path.join(platformDir, `post_direct_${Date.now()}.md`);
      fs.writeFileSync(
        postFile,
        [
          `---`,
          `id: ${result.id}`,
          `platform: ${platform}`,
          `posted_at: ${result.posted_at}`,
          `simulated: ${result.simulated || false}`,
          `---`,
          ``,
          result.content || content,
        ].join("\n"),
        "utf-8"
      );

      return {
        content: [
          {
            type: "text",
            text: [
              `Posted to ${platform}${result.simulated ? " (SIMULATED)" : ""}`,
              ``,
              `**Post ID:** ${result.id}`,
              `**Characters:** ${(result.content || content).length}/${CHAR_LIMITS[platform]}`,
              result.url ? `**URL:** ${result.url}` : "",
            ]
              .filter(Boolean)
              .join("\n"),
          },
        ],
      };
    } catch (err) {
      return {
        content: [
          {
            type: "text",
            text: `Failed to post to ${platform}: ${err.message}`,
          },
        ],
      };
    }
  }
);

// ── Tool 6: get_engagement ──
server.tool(
  "get_engagement",
  "Get engagement metrics for a platform (likes, shares, reach, etc.)",
  {
    platform: z
      .enum(["twitter", "facebook", "instagram"])
      .describe("Platform to query"),
    period: z
      .enum(["day", "week", "month"])
      .optional()
      .default("week")
      .describe("Time period"),
  },
  async ({ platform, period }) => {
    log("INFO", "get_engagement called", { platform, period });

    try {
      const metrics = await social.getEngagement(platform, period);

      const lines = [
        `# ${capitalize(platform)} Engagement — ${period}${metrics.simulated ? " (SIMULATED)" : ""}`,
        ``,
        `| Metric | Value |`,
        `|--------|-------|`,
      ];

      for (const [key, value] of Object.entries(metrics)) {
        if (
          !["platform", "period", "simulated", "fetched_at"].includes(key)
        ) {
          lines.push(
            `| ${key.replace(/_/g, " ")} | ${typeof value === "number" ? value.toLocaleString() : value} |`
          );
        }
      }

      lines.push(``, `*Fetched: ${metrics.fetched_at}*`);

      return { content: [{ type: "text", text: lines.join("\n") }] };
    } catch (err) {
      return {
        content: [{ type: "text", text: `Failed: ${err.message}` }],
      };
    }
  }
);

// ── Tool 7: get_rate_limits ──
server.tool(
  "get_rate_limits",
  "Check rate limit status for all platforms",
  {},
  async () => {
    log("INFO", "get_rate_limits called");

    const lines = [
      `# Rate Limit Status`,
      ``,
      `| Platform | Available | Tokens Remaining | Max |`,
      `|----------|-----------|------------------|-----|`,
    ];

    PLATFORMS.forEach((p) => {
      const status = social.getRateLimitStatus(p);
      lines.push(
        `| ${capitalize(p)} | ${status.available ? "Yes" : "THROTTLED"} | ${status.tokens} | ${status.maxTokens} |`
      );
    });

    return { content: [{ type: "text", text: lines.join("\n") }] };
  }
);

// ── Tool 8: generate_summary ──
server.tool(
  "generate_summary",
  "Generate a weekly social media summary across all platforms. Saved to /Social/Summaries/.",
  {
    week_label: z
      .string()
      .optional()
      .describe("Label for the week (e.g. 'Week 3 Feb 2026')"),
  },
  async ({ week_label }) => {
    log("INFO", "generate_summary called", { week_label });

    const label =
      week_label || `Week of ${new Date().toISOString().split("T")[0]}`;

    // Gather engagement from all platforms
    const engagements = {};
    for (const p of PLATFORMS) {
      try {
        engagements[p] = await social.getEngagement(p, "week");
      } catch {
        engagements[p] = { posts: 0, simulated: true };
      }
    }

    const tw = engagements.twitter || {};
    const fb = engagements.facebook || {};
    const ig = engagements.instagram || {};

    const totalPosts =
      (tw.posts || 0) + (fb.posts || 0) + (ig.posts || 0);
    const totalLikes =
      (tw.total_likes || 0) + (fb.total_likes || 0) + (ig.total_likes || 0);
    const totalEngagement =
      totalLikes +
      (tw.total_retweets || 0) +
      (fb.total_comments || 0) +
      (fb.total_shares || 0) +
      (ig.total_comments || 0) +
      (ig.total_saves || 0);

    // Scan /Social/ folders for posted files
    const postedFiles = {};
    for (const p of ["Twitter", "Facebook", "Instagram"]) {
      const dir = path.join(SOCIAL_DIR, p);
      postedFiles[p.toLowerCase()] = fs.existsSync(dir)
        ? fs.readdirSync(dir).filter((f) => f.startsWith("post_")).length
        : 0;
    }

    const summaryContent = [
      `# Weekly Social Media Summary — ${label}`,
      ``,
      `**Generated:** ${new Date().toISOString()}`,
      `**Mode:** ${social.isSimulated ? "SIMULATED" : "LIVE"}`,
      ``,
      `## Cross-Platform Overview`,
      ``,
      `| Metric | Twitter/X | Facebook | Instagram | Total |`,
      `|--------|-----------|----------|-----------|-------|`,
      `| Posts | ${tw.posts || 0} | ${fb.posts || 0} | ${ig.posts || 0} | ${totalPosts} |`,
      `| Likes | ${tw.total_likes || 0} | ${fb.total_likes || 0} | ${ig.total_likes || 0} | ${totalLikes} |`,
      `| Impressions/Reach | ${tw.total_impressions || 0} | ${fb.total_reach || 0} | ${ig.total_reach || 0} | ${(tw.total_impressions || 0) + (fb.total_reach || 0) + (ig.total_reach || 0)} |`,
      ``,
      `## Platform Details`,
      ``,
      `### Twitter/X`,
      `- Posts: ${tw.posts || 0}`,
      `- Retweets: ${tw.total_retweets || 0}`,
      `- Replies: ${tw.total_replies || 0}`,
      `- Followers gained: ${tw.followers_gained || 0}`,
      tw.top_post ? `- Top post: "${tw.top_post}"` : "",
      ``,
      `### Facebook`,
      `- Posts: ${fb.posts || 0}`,
      `- Comments: ${fb.total_comments || 0}`,
      `- Shares: ${fb.total_shares || 0}`,
      `- Page views: ${fb.page_views || 0}`,
      fb.top_post ? `- Top post: "${fb.top_post}"` : "",
      ``,
      `### Instagram`,
      `- Posts: ${ig.posts || 0}`,
      `- Comments: ${ig.total_comments || 0}`,
      `- Saves: ${ig.total_saves || 0}`,
      `- Profile visits: ${ig.profile_visits || 0}`,
      ig.top_post ? `- Top post: "${ig.top_post}"` : "",
      ``,
      `## Key Metrics`,
      ``,
      `- **Total posts this week:** ${totalPosts}`,
      `- **Total engagement:** ${totalEngagement}`,
      `- **Engagement rate:** ${totalPosts > 0 ? (totalEngagement / totalPosts).toFixed(1) : 0} per post`,
      `- **Files in vault:** Twitter(${postedFiles.twitter}), Facebook(${postedFiles.facebook}), Instagram(${postedFiles.instagram})`,
      ``,
      `## Pending Drafts`,
      ``,
    ].filter(Boolean);

    const pendingDrafts = Array.from(drafts.values()).filter(
      (d) => d.status === "pending"
    );
    if (pendingDrafts.length > 0) {
      summaryContent.push(
        `| ID | Platform | Category | Created |`,
        `|----|----------|----------|---------|`
      );
      pendingDrafts.forEach((d) => {
        summaryContent.push(
          `| ${d.id} | ${d.platform} | ${d.category} | ${d.created.split("T")[0]} |`
        );
      });
    } else {
      summaryContent.push(`*No pending drafts.*`);
    }

    summaryContent.push(
      ``,
      `---`,
      `*Generated by AI Employee Social Media MCP Server*`
    );

    const summaryStr = summaryContent.join("\n");

    // Save summary
    const filename = `summary_${new Date().toISOString().split("T")[0]}_${Date.now()}.md`;
    const summaryPath = path.join(SUMMARIES_DIR, filename);
    fs.writeFileSync(summaryPath, summaryStr, "utf-8");

    log("INFO", `Weekly summary saved: ${filename}`);

    return {
      content: [
        {
          type: "text",
          text: `Summary saved: /Social/Summaries/${filename}\n\n${summaryStr}`,
        },
      ],
    };
  }
);

// ── Tool 9: generate_ceo_briefing ──
server.tool(
  "generate_ceo_briefing",
  "Generate a CEO briefing that includes social media metrics, engagement trends, and recommendations.",
  {
    week_label: z
      .string()
      .optional()
      .describe("Label for the briefing period"),
    include_recommendations: z
      .boolean()
      .optional()
      .default(true)
      .describe("Include AI-generated recommendations"),
  },
  async ({ week_label, include_recommendations }) => {
    log("INFO", "generate_ceo_briefing called", { week_label });

    const label =
      week_label || `Week of ${new Date().toISOString().split("T")[0]}`;

    // Gather all engagement data
    const engagements = {};
    for (const p of PLATFORMS) {
      try {
        engagements[p] = await social.getEngagement(p, "week");
      } catch {
        engagements[p] = { posts: 0 };
      }
    }

    const tw = engagements.twitter || {};
    const fb = engagements.facebook || {};
    const ig = engagements.instagram || {};

    const totalPosts =
      (tw.posts || 0) + (fb.posts || 0) + (ig.posts || 0);
    const totalReach =
      (tw.total_impressions || 0) +
      (fb.total_reach || 0) +
      (ig.total_reach || 0);
    const totalEngagement =
      (tw.total_likes || 0) +
      (tw.total_retweets || 0) +
      (fb.total_likes || 0) +
      (fb.total_comments || 0) +
      (fb.total_shares || 0) +
      (ig.total_likes || 0) +
      (ig.total_comments || 0) +
      (ig.total_saves || 0);

    // Read Social Goals if available
    let goalsContext = "No social goals file found.";
    if (fs.existsSync(GOALS_FILE)) {
      goalsContext = fs.readFileSync(GOALS_FILE, "utf-8");
    }

    const briefing = [
      `# CEO Briefing — Social Media — ${label}`,
      ``,
      `**Prepared:** ${new Date().toISOString()}`,
      `**Mode:** ${social.isSimulated ? "SIMULATED" : "LIVE"}`,
      ``,
      `---`,
      ``,
      `## Executive Summary`,
      ``,
      `This week, the company published **${totalPosts} posts** across 3 platforms,`,
      `reaching **${totalReach.toLocaleString()} people** with **${totalEngagement.toLocaleString()} total engagements**.`,
      ``,
      `## Social Media Scorecard`,
      ``,
      `| Platform | Posts | Reach | Likes | Engagement | Top Content |`,
      `|----------|-------|-------|-------|------------|-------------|`,
      `| Twitter/X | ${tw.posts || 0} | ${(tw.total_impressions || 0).toLocaleString()} | ${tw.total_likes || 0} | ${(tw.total_likes || 0) + (tw.total_retweets || 0)} | ${tw.top_post ? `"${tw.top_post.substring(0, 40)}..."` : "N/A"} |`,
      `| Facebook | ${fb.posts || 0} | ${(fb.total_reach || 0).toLocaleString()} | ${fb.total_likes || 0} | ${(fb.total_likes || 0) + (fb.total_comments || 0) + (fb.total_shares || 0)} | ${fb.top_post ? `"${fb.top_post.substring(0, 40)}..."` : "N/A"} |`,
      `| Instagram | ${ig.posts || 0} | ${(ig.total_reach || 0).toLocaleString()} | ${ig.total_likes || 0} | ${(ig.total_likes || 0) + (ig.total_comments || 0) + (ig.total_saves || 0)} | ${ig.top_post ? `"${ig.top_post.substring(0, 40)}..."` : "N/A"} |`,
      `| **Total** | **${totalPosts}** | **${totalReach.toLocaleString()}** | **${(tw.total_likes || 0) + (fb.total_likes || 0) + (ig.total_likes || 0)}** | **${totalEngagement}** | |`,
      ``,
      `## Key Highlights`,
      ``,
      `- **Best performing platform:** ${_bestPlatform(tw, fb, ig)}`,
      `- **Audience growth:** Twitter +${tw.followers_gained || 0} followers, Instagram +${ig.profile_visits || 0} profile visits`,
      `- **Content engagement rate:** ${totalPosts > 0 ? (totalEngagement / totalPosts).toFixed(1) : 0} engagements per post`,
      ``,
      `## Pending Actions`,
      ``,
      `- ${Array.from(drafts.values()).filter((d) => d.status === "pending").length} draft posts awaiting approval`,
      `- Rate limits: ${PLATFORMS.map((p) => `${capitalize(p)}(${social.getRateLimitStatus(p).tokens} remaining)`).join(", ")}`,
    ];

    if (include_recommendations) {
      briefing.push(
        ``,
        `## AI Recommendations`,
        ``,
        `Based on this week's performance:`,
        ``,
        `1. **${_bestPlatform(tw, fb, ig)}** is driving the most engagement — consider increasing posting frequency`,
        `2. ${(tw.total_impressions || 0) > (fb.total_reach || 0) ? "Twitter/X impressions lead" : "Facebook reach leads"} — allocate more budget to the top performer`,
        `3. Instagram saves (${ig.total_saves || 0}) indicate high-value content — repurpose top posts`,
        `4. Engagement rate of ${totalPosts > 0 ? (totalEngagement / totalPosts).toFixed(1) : 0}/post ${totalPosts > 0 && totalEngagement / totalPosts > 20 ? "exceeds" : "is below"} industry average (~20)`,
        `5. Ensure all posts align with Social_Goals.md strategy`,
        ``
      );
    }

    briefing.push(
      ``,
      `---`,
      `*Generated by AI Employee Social Media MCP Server*`,
      `*For full details, see /Social/Summaries/*`
    );

    const briefingStr = briefing.join("\n");

    // Save briefing
    const filename = `ceo_briefing_${new Date().toISOString().split("T")[0]}_${Date.now()}.md`;
    const briefingPath = path.join(SUMMARIES_DIR, filename);
    fs.writeFileSync(briefingPath, briefingStr, "utf-8");

    log("INFO", `CEO briefing saved: ${filename}`);

    return {
      content: [
        {
          type: "text",
          text: `CEO Briefing saved: /Social/Summaries/${filename}\n\n${briefingStr}`,
        },
      ],
    };
  }
);

// ── Tool 10: get_social_goals ──
server.tool(
  "get_social_goals",
  "Read the Social_Goals.md file for content strategy and posting guidelines",
  {},
  async () => {
    log("INFO", "get_social_goals called");

    if (!fs.existsSync(GOALS_FILE)) {
      return {
        content: [
          {
            type: "text",
            text: "Social_Goals.md not found. Create it at /Social/Social_Goals.md.",
          },
        ],
      };
    }

    const content = fs.readFileSync(GOALS_FILE, "utf-8");
    return { content: [{ type: "text", text: content }] };
  }
);

// ---------------------------------------------------------------------------
// Resource: Social Goals
// ---------------------------------------------------------------------------
server.resource(
  "social-goals",
  "vault://Social/Social_Goals.md",
  async (uri) => {
    let content = "No social goals defined yet.";
    if (fs.existsSync(GOALS_FILE)) {
      content = fs.readFileSync(GOALS_FILE, "utf-8");
    }
    return {
      contents: [{ uri: uri.href, text: content, mimeType: "text/markdown" }],
    };
  }
);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function capitalize(s) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function _bestPlatform(tw, fb, ig) {
  const scores = {
    "Twitter/X":
      (tw.total_likes || 0) + (tw.total_retweets || 0),
    Facebook:
      (fb.total_likes || 0) + (fb.total_comments || 0) + (fb.total_shares || 0),
    Instagram:
      (ig.total_likes || 0) + (ig.total_comments || 0) + (ig.total_saves || 0),
  };
  return Object.entries(scores).sort((a, b) => b[1] - a[1])[0][0];
}

// ---------------------------------------------------------------------------
// Start Server
// ---------------------------------------------------------------------------
async function main() {
  log("INFO", "Social Media MCP Server starting", {
    simulate: social.isSimulated,
    dry_run: DRY_RUN,
  });

  const transport = new StdioServerTransport();
  await server.connect(transport);
  log("INFO", "Social Media MCP Server connected via stdio");
}

main().catch((err) => {
  log("ERROR", `Server failed: ${err.message}`);
  process.exit(1);
});
