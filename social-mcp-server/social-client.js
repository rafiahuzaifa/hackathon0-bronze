/**
 * social-client.js — Unified Social Media API Client
 *
 * Handles Twitter/X, Facebook, and Instagram APIs with:
 *   - Rate limiting (token-bucket per platform)
 *   - 3x retry with exponential backoff
 *   - Simulation mode (default ON)
 *
 * Environment Variables:
 *   TWITTER_BEARER_TOKEN, TWITTER_API_KEY, TWITTER_API_SECRET,
 *   TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
 *   FACEBOOK_PAGE_TOKEN, FACEBOOK_PAGE_ID
 *   INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ID
 *   SOCIAL_SIMULATE  (default: "true")
 */

const https = require("https");
const fs = require("fs");
const path = require("path");

const LOG_FILE = path.join(__dirname, "social-mcp.log");

function log(level, msg, data = null) {
  const ts = new Date().toISOString();
  const entry = `[${ts}] [${level}] ${msg}${data ? " " + JSON.stringify(data) : ""}`;
  fs.appendFileSync(LOG_FILE, entry + "\n", "utf-8");
}

// ---------------------------------------------------------------------------
// Rate Limiter — Token Bucket per platform
// ---------------------------------------------------------------------------
class RateLimiter {
  constructor(limits) {
    // limits: { twitter: { maxTokens, refillRate(per min) }, ... }
    this.buckets = {};
    for (const [platform, cfg] of Object.entries(limits)) {
      this.buckets[platform] = {
        tokens: cfg.maxTokens,
        maxTokens: cfg.maxTokens,
        refillRate: cfg.refillRate,
        lastRefill: Date.now(),
      };
    }
  }

  async acquire(platform) {
    const bucket = this.buckets[platform];
    if (!bucket) return true; // unknown platform = no limit

    // Refill tokens based on elapsed time
    const now = Date.now();
    const elapsed = (now - bucket.lastRefill) / 60000; // minutes
    bucket.tokens = Math.min(
      bucket.maxTokens,
      bucket.tokens + elapsed * bucket.refillRate
    );
    bucket.lastRefill = now;

    if (bucket.tokens >= 1) {
      bucket.tokens -= 1;
      return true;
    }

    // Wait for next token
    const waitMs = ((1 - bucket.tokens) / bucket.refillRate) * 60000;
    log("WARN", `Rate limited on ${platform}, waiting ${Math.ceil(waitMs)}ms`);
    await new Promise((r) => setTimeout(r, waitMs));
    bucket.tokens = 0;
    bucket.lastRefill = Date.now();
    return true;
  }

  getStatus(platform) {
    const bucket = this.buckets[platform];
    if (!bucket) return { available: true, tokens: Infinity };
    return {
      available: bucket.tokens >= 1,
      tokens: Math.floor(bucket.tokens),
      maxTokens: bucket.maxTokens,
    };
  }
}

// Platform rate limits (conservative)
const DEFAULT_LIMITS = {
  twitter: { maxTokens: 50, refillRate: 50 },   // 50 tweets/15min window
  facebook: { maxTokens: 60, refillRate: 60 },   // 60 posts/hour
  instagram: { maxTokens: 25, refillRate: 25 },  // 25 posts/day (conservative)
};

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------
const DEFAULT_CONFIG = {
  simulate: process.env.SOCIAL_SIMULATE !== "false",
  twitter: {
    bearerToken: process.env.TWITTER_BEARER_TOKEN || "",
    apiKey: process.env.TWITTER_API_KEY || "",
    apiSecret: process.env.TWITTER_API_SECRET || "",
    accessToken: process.env.TWITTER_ACCESS_TOKEN || "",
    accessSecret: process.env.TWITTER_ACCESS_SECRET || "",
  },
  facebook: {
    pageToken: process.env.FACEBOOK_PAGE_TOKEN || "",
    pageId: process.env.FACEBOOK_PAGE_ID || "",
  },
  instagram: {
    accessToken: process.env.INSTAGRAM_ACCESS_TOKEN || "",
    businessId: process.env.INSTAGRAM_BUSINESS_ID || "",
  },
};

const MAX_RETRIES = 3;
const RETRY_BASE_DELAY_MS = 1000;

// ---------------------------------------------------------------------------
// HTTP Transport
// ---------------------------------------------------------------------------
function _httpsRequest(options, body = null) {
  return new Promise((resolve, reject) => {
    const req = https.request(options, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        try {
          resolve({ status: res.statusCode, data: JSON.parse(data) });
        } catch {
          resolve({ status: res.statusCode, data: data });
        }
      });
    });
    req.on("error", reject);
    req.on("timeout", () => {
      req.destroy();
      reject(new Error("Request timed out"));
    });
    req.setTimeout(15000);
    if (body) req.write(body);
    req.end();
  });
}

async function apiCall(options, body, retries = MAX_RETRIES) {
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const result = await _httpsRequest(options, body);
      if (result.status === 429) {
        throw new Error("Rate limited by API (HTTP 429)");
      }
      if (result.status >= 400) {
        const errMsg =
          typeof result.data === "object"
            ? JSON.stringify(result.data)
            : result.data;
        throw new Error(`API Error ${result.status}: ${errMsg}`);
      }
      return result.data;
    } catch (err) {
      log("WARN", `API attempt ${attempt}/${retries} failed: ${err.message}`);
      if (attempt === retries) {
        log("ERROR", `API failed after ${retries} retries`, {
          error: err.message,
        });
        throw err;
      }
      const delay = RETRY_BASE_DELAY_MS * Math.pow(2, attempt - 1);
      await new Promise((r) => setTimeout(r, delay));
    }
  }
}

// ---------------------------------------------------------------------------
// Social Media Client
// ---------------------------------------------------------------------------
class SocialClient {
  constructor(config = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    if (config.twitter)
      this.config.twitter = { ...DEFAULT_CONFIG.twitter, ...config.twitter };
    if (config.facebook)
      this.config.facebook = { ...DEFAULT_CONFIG.facebook, ...config.facebook };
    if (config.instagram)
      this.config.instagram = {
        ...DEFAULT_CONFIG.instagram,
        ...config.instagram,
      };

    this.rateLimiter = new RateLimiter(DEFAULT_LIMITS);
    this._simPostCounter = 5000;
    this._simPosts = [];
    this._simEngagement = new Map();
  }

  get isSimulated() {
    return this.config.simulate;
  }

  // ── Post to any platform ──
  async post(platform, content, options = {}) {
    await this.rateLimiter.acquire(platform);

    if (this.isSimulated) {
      return this._simPost(platform, content, options);
    }

    switch (platform) {
      case "twitter":
        return this._postTwitter(content, options);
      case "facebook":
        return this._postFacebook(content, options);
      case "instagram":
        return this._postInstagram(content, options);
      default:
        throw new Error(`Unknown platform: ${platform}`);
    }
  }

  // ── Twitter/X API v2 ──
  async _postTwitter(content, options) {
    const body = JSON.stringify({ text: content.substring(0, 280) });
    const result = await apiCall(
      {
        hostname: "api.twitter.com",
        path: "/2/tweets",
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.config.twitter.bearerToken}`,
          "Content-Length": Buffer.byteLength(body),
        },
      },
      body
    );

    return {
      id: result.data?.id || `TW-${Date.now()}`,
      platform: "twitter",
      content: content.substring(0, 280),
      url: `https://twitter.com/i/status/${result.data?.id}`,
      posted_at: new Date().toISOString(),
    };
  }

  // ── Facebook Graph API ──
  async _postFacebook(content, options) {
    const pageId = this.config.facebook.pageId;
    const params = new URLSearchParams({
      message: content,
      access_token: this.config.facebook.pageToken,
    });

    const result = await apiCall(
      {
        hostname: "graph.facebook.com",
        path: `/v19.0/${pageId}/feed?${params.toString()}`,
        method: "POST",
        headers: { "Content-Type": "application/json" },
      },
      null
    );

    return {
      id: result.id || `FB-${Date.now()}`,
      platform: "facebook",
      content,
      url: `https://facebook.com/${result.id}`,
      posted_at: new Date().toISOString(),
    };
  }

  // ── Instagram Graph API (business accounts) ──
  async _postInstagram(content, options) {
    const bizId = this.config.instagram.businessId;
    const token = this.config.instagram.accessToken;

    // Instagram requires an image_url for feed posts
    // For text-only "caption" posts, we use a placeholder approach
    const imageUrl =
      options.image_url || "https://via.placeholder.com/1080x1080.png";

    // Step 1: Create media container
    const containerParams = new URLSearchParams({
      image_url: imageUrl,
      caption: content,
      access_token: token,
    });

    const container = await apiCall(
      {
        hostname: "graph.facebook.com",
        path: `/v19.0/${bizId}/media?${containerParams.toString()}`,
        method: "POST",
        headers: { "Content-Type": "application/json" },
      },
      null
    );

    // Step 2: Publish container
    const publishParams = new URLSearchParams({
      creation_id: container.id,
      access_token: token,
    });

    const published = await apiCall(
      {
        hostname: "graph.facebook.com",
        path: `/v19.0/${bizId}/media_publish?${publishParams.toString()}`,
        method: "POST",
        headers: { "Content-Type": "application/json" },
      },
      null
    );

    return {
      id: published.id || `IG-${Date.now()}`,
      platform: "instagram",
      content,
      posted_at: new Date().toISOString(),
    };
  }

  // ── Get Engagement Metrics ──
  async getEngagement(platform, period = "week") {
    if (this.isSimulated) {
      return this._simEngagementData(platform, period);
    }

    switch (platform) {
      case "twitter":
        return this._getTwitterEngagement(period);
      case "facebook":
        return this._getFacebookEngagement(period);
      case "instagram":
        return this._getInstagramEngagement(period);
      default:
        throw new Error(`Unknown platform: ${platform}`);
    }
  }

  async _getTwitterEngagement(period) {
    // Twitter API v2: get user tweets + metrics
    const result = await apiCall(
      {
        hostname: "api.twitter.com",
        path: `/2/users/me/tweets?max_results=10&tweet.fields=public_metrics,created_at`,
        method: "GET",
        headers: {
          Authorization: `Bearer ${this.config.twitter.bearerToken}`,
        },
      },
      null
    );

    const tweets = result.data || [];
    return {
      platform: "twitter",
      period,
      posts: tweets.length,
      total_likes: tweets.reduce(
        (s, t) => s + (t.public_metrics?.like_count || 0),
        0
      ),
      total_retweets: tweets.reduce(
        (s, t) => s + (t.public_metrics?.retweet_count || 0),
        0
      ),
      total_impressions: tweets.reduce(
        (s, t) => s + (t.public_metrics?.impression_count || 0),
        0
      ),
      fetched_at: new Date().toISOString(),
    };
  }

  async _getFacebookEngagement(period) {
    const pageId = this.config.facebook.pageId;
    const token = this.config.facebook.pageToken;

    const result = await apiCall(
      {
        hostname: "graph.facebook.com",
        path: `/v19.0/${pageId}/posts?fields=message,likes.summary(true),comments.summary(true),shares&limit=10&access_token=${token}`,
        method: "GET",
        headers: {},
      },
      null
    );

    const posts = result.data || [];
    return {
      platform: "facebook",
      period,
      posts: posts.length,
      total_likes: posts.reduce(
        (s, p) => s + (p.likes?.summary?.total_count || 0),
        0
      ),
      total_comments: posts.reduce(
        (s, p) => s + (p.comments?.summary?.total_count || 0),
        0
      ),
      total_shares: posts.reduce(
        (s, p) => s + (p.shares?.count || 0),
        0
      ),
      fetched_at: new Date().toISOString(),
    };
  }

  async _getInstagramEngagement(period) {
    const bizId = this.config.instagram.businessId;
    const token = this.config.instagram.accessToken;

    const result = await apiCall(
      {
        hostname: "graph.facebook.com",
        path: `/v19.0/${bizId}/media?fields=like_count,comments_count,caption,timestamp&limit=10&access_token=${token}`,
        method: "GET",
        headers: {},
      },
      null
    );

    const media = result.data || [];
    return {
      platform: "instagram",
      period,
      posts: media.length,
      total_likes: media.reduce((s, m) => s + (m.like_count || 0), 0),
      total_comments: media.reduce(
        (s, m) => s + (m.comments_count || 0),
        0
      ),
      fetched_at: new Date().toISOString(),
    };
  }

  // ── Rate Limit Status ──
  getRateLimitStatus(platform) {
    return {
      platform,
      ...this.rateLimiter.getStatus(platform),
      simulated: this.isSimulated,
    };
  }

  // ── Simulation Methods ──

  _simPost(platform, content, options) {
    this._simPostCounter++;
    const id = `SIM-${platform.toUpperCase()}-${this._simPostCounter}`;

    const charLimit =
      platform === "twitter" ? 280 : platform === "instagram" ? 2200 : 63206;
    const truncated = content.substring(0, charLimit);

    const post = {
      id,
      platform,
      content: truncated,
      char_count: truncated.length,
      char_limit: charLimit,
      posted_at: new Date().toISOString(),
      simulated: true,
      hashtags: (truncated.match(/#\w+/g) || []).length,
    };

    this._simPosts.push(post);
    log("INFO", `[SIM] Posted to ${platform}: ${id}`, {
      chars: truncated.length,
    });
    return post;
  }

  _simEngagementData(platform, period) {
    const bases = {
      twitter: {
        posts: 12,
        total_likes: 245,
        total_retweets: 38,
        total_replies: 15,
        total_impressions: 8400,
        top_post: "Excited to announce our Q1 results! #growth",
        followers_gained: 23,
      },
      facebook: {
        posts: 8,
        total_likes: 180,
        total_comments: 32,
        total_shares: 14,
        total_reach: 5200,
        top_post: "Check out our latest case study on digital transformation",
        page_views: 890,
      },
      instagram: {
        posts: 6,
        total_likes: 320,
        total_comments: 28,
        total_saves: 45,
        total_reach: 4100,
        top_post: "Behind the scenes of our product launch",
        profile_visits: 210,
      },
    };

    return {
      platform,
      period,
      simulated: true,
      ...(bases[platform] || bases.twitter),
      fetched_at: new Date().toISOString(),
    };
  }

  getSimPosts() {
    return [...this._simPosts];
  }
}

module.exports = { SocialClient, RateLimiter, DEFAULT_CONFIG };
