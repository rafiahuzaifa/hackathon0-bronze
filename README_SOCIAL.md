# Social Media Integration — Setup Guide

> AI Employee · Gold Tier · Panaversity Hackathon 2026

This guide walks through setting up real social media integrations for all 4 platforms. Each watcher uses the platform's official API with OAuth authentication, Claude-powered content adaptation, and vault-based approval flows.

---

## Architecture

```
Your Content
    │
    ▼
SocialMediaManager.post_to_all()
    │
    ├─► Claude adapts content per platform
    ├─► Risk assessment (low / medium / high)
    │
    ├─[low risk]────► Post directly via API
    ├─[medium risk]──► vault/Pending_Approval/ (auto-approve in 1h)
    └─[high risk]────► vault/Pending_Approval/ (manual approval required)
                            │
                            ▼
                      Dashboard UI → Approve → vault/Approved/
                            │
                            ▼
                      Orchestrator dispatches via MCP
```

---

## Quick Setup

```bash
cd ai_employee
pip install -r requirements.txt
python -m setup.oauth_setup
```

The interactive CLI will guide you through each platform.

---

## Platform 1: LinkedIn

### Developer App
1. Go to [LinkedIn Developer Portal](https://developer.linkedin.com/apps)
2. Create app → Add **Sign In with LinkedIn** + **Share on LinkedIn** products
3. Under **Auth** tab → copy **Client ID** and **Client Secret**
4. Add redirect URL: `http://localhost:8080/callback`

### OAuth Setup
```bash
python -m setup.oauth_setup
# Select: 1 - LinkedIn
# Browser opens → authorize → token saved to .env automatically
```

### What gets saved
```
LINKEDIN_CLIENT_ID=...
LINKEDIN_CLIENT_SECRET=...
LINKEDIN_ACCESS_TOKEN=...          # 60-day token
LINKEDIN_REFRESH_TOKEN=...         # Used to auto-renew
LINKEDIN_TOKEN_EXPIRY=...          # Unix ts — checked before each call
LINKEDIN_PERSON_URN=urn:li:person:XXXXX
```

### Capabilities
| Feature | Method |
|---------|--------|
| Post text | `POST /v2/ugcPosts` |
| Post with image | 3-step: register → upload → post |
| Read messages | `GET /v2/conversations` |
| Check connection requests | `GET /v2/invitations` |
| Monitor post comments | `GET /v2/ugcPosts` + comments |
| Analytics | `GET /v2/socialMetadata/{post_id}` |

---

## Platform 2: Twitter / X

### Developer App
1. Go to [Twitter Developer Portal](https://developer.twitter.com/en/portal/dashboard)
2. Create Project → Create App
3. Set **App permissions** → Read and Write + Direct Messages
4. Under **Keys and Tokens** → copy all 5 credentials
5. Set callback URL: `http://localhost:8080/callback`

### OAuth Setup
```bash
python -m setup.oauth_setup
# Select: 2 - Twitter
# Enter 5 credentials when prompted → verified + saved to .env
```

### What gets saved
```
TWITTER_API_KEY=...
TWITTER_API_SECRET=...
TWITTER_ACCESS_TOKEN=...
TWITTER_ACCESS_TOKEN_SECRET=...
TWITTER_BEARER_TOKEN=...
TWITTER_MY_USER_ID=...             # Numeric user ID (auto-fetched)
```

### Capabilities
| Feature | API |
|---------|-----|
| Post tweet | `POST /2/tweets` (Tweepy v4) |
| Post thread | Sequential tweets, each replying to previous |
| Upload media | `POST /1.1/media/upload` (v1 API) |
| Monitor mentions | `GET /2/users/{id}/mentions` with `since_id` |
| Search keywords | `GET /2/tweets/search/recent` |
| Get analytics | `GET /2/tweets/{id}?tweet.fields=public_metrics` |
| Delete tweet | `DELETE /2/tweets/{id}` |

---

## Platform 3: Facebook

### Developer App
1. Go to [Facebook for Developers](https://developers.facebook.com/apps)
2. Create App → **Business** type
3. Add product: **Messenger** + **Pages API**
4. Under **App Review** → request `pages_manage_posts`, `pages_read_engagement`, `pages_messaging`
5. Generate **Page Access Token** from Graph API Explorer

### OAuth Setup
```bash
python -m setup.oauth_setup
# Select: 3 - Facebook
# Paste short-lived token → exchanged for 60-day token automatically
# Lists your pages → select page → saves PAGE_ID
```

### What gets saved
```
FACEBOOK_APP_ID=...
FACEBOOK_APP_SECRET=...
FACEBOOK_PAGE_ACCESS_TOKEN=...     # Short-lived (input)
FACEBOOK_LONG_LIVED_TOKEN=...      # 60-day (auto-exchanged)
FACEBOOK_PAGE_ID=...
```

### Capabilities
| Feature | Endpoint |
|---------|----------|
| Post text | `POST /{page_id}/feed` |
| Post with photo | `POST /{page_id}/photos` |
| Post with video | `POST /{page_id}/videos` |
| Read Messenger | `GET /{page_id}/conversations` |
| Monitor comments | `GET /{page_id}/feed?fields=comments` |
| Reply to comment | `POST /{comment_id}/comments` |
| Post insights | `GET /{post_id}/insights` |

---

## Platform 4: Instagram

### Requirements
- Instagram **Business** or **Creator** account
- Account must be linked to a Facebook Page
- Facebook app must have `instagram_basic`, `instagram_content_publish` permissions

### OAuth Setup
```bash
python -m setup.oauth_setup
# Select: 3 - Facebook/Instagram (shared flow)
# IG Account ID is fetched automatically via: GET /{page_id}?fields=instagram_business_account
```

### What gets saved
```
INSTAGRAM_ACCESS_TOKEN=...         # Same as FACEBOOK_LONG_LIVED_TOKEN
INSTAGRAM_ACCOUNT_ID=...           # Numeric IG account ID
```

### Capabilities
| Feature | Flow |
|---------|------|
| Image post | Create container → publish |
| Carousel post | N child containers → carousel container → publish |
| Reel | Create container (media_type=REELS) → poll status → publish |
| Reply to comment | `POST /{comment_id}/replies` |
| Monitor comments | `GET /{ig_user_id}/media` → per-post comments |
| Monitor mentions | `GET /{ig_user_id}/tags` |
| Search hashtags | `ig_hashtag_search` → recent_media |
| Media insights | `GET /{media_id}/insights` |

---

## Content Flow

### Vault Directories
```
vault/
├── Needs_Action/      ← Raw incoming events (emails, DMs, mentions)
├── Pending_Approval/  ← Posts awaiting human review
│   └── SOCIAL_{PLATFORM}_{ts}.md
├── Approved/          ← Human-approved → orchestrator dispatches
├── Done/              ← Successfully posted
├── Failed/            ← Failed posts (with error details)
├── Scheduled/         ← Future-dated posts
│   └── {PLATFORM}_{ts}.md  ← status: pending → executing → done
└── Cancelled/         ← Cancelled scheduled posts
```

### Scheduled Post Frontmatter
```yaml
---
platform: twitter
content: "Your tweet text here"
scheduled_time: "2026-03-20T09:00:00"
recurring: none              # none | daily | weekly
status: pending
created_at: "2026-03-16T14:30:00"
image_url:                   # optional public URL
---
```

---

## Environment Variables Reference

| Variable | Platform | Description |
|----------|----------|-------------|
| `LINKEDIN_ACCESS_TOKEN` | LinkedIn | OAuth2 access token |
| `LINKEDIN_REFRESH_TOKEN` | LinkedIn | Used to auto-renew access token |
| `LINKEDIN_TOKEN_EXPIRY` | LinkedIn | Unix timestamp of token expiry |
| `LINKEDIN_PERSON_URN` | LinkedIn | `urn:li:person:XXXXX` |
| `TWITTER_API_KEY` | Twitter | App API key (OAuth 1.0a) |
| `TWITTER_BEARER_TOKEN` | Twitter | App-only bearer token (reading) |
| `TWITTER_MY_USER_ID` | Twitter | Your numeric user ID |
| `FACEBOOK_LONG_LIVED_TOKEN` | Facebook | 60-day page access token |
| `FACEBOOK_PAGE_ID` | Facebook | Numeric page ID |
| `INSTAGRAM_ACCESS_TOKEN` | Instagram | Same as Facebook long-lived token |
| `INSTAGRAM_ACCOUNT_ID` | Instagram | Numeric IG Business Account ID |

---

## Testing Connections

```bash
python -m setup.oauth_setup
# Select: 5 - Test all connections
```

Output:
```
LinkedIn  ✅  Connected as John Doe (urn:li:person:XXXXX)
Twitter   ✅  Connected as @ai_employee (id: 12345678)
Facebook  ✅  Page: AI Employee Page (id: 987654321)
Instagram ✅  Account: @ai_employee (id: 111222333)
```

---

## Rate Limits

| Platform | Post limit enforced | API limit |
|----------|--------------------|-----------|
| LinkedIn | 5 posts/hour | 100 req/day (free tier) |
| Twitter | 5 posts/hour | 500 tweets/month (Basic) |
| Facebook | 5 posts/hour | No strict limit |
| Instagram | 5 posts/hour | 50 media publishes/day |

All watchers enforce `DRY_RUN=true` by default — no real API calls until you set `DRY_RUN=false`.

---

## Dashboard Social Page

Navigate to **Social Media** in the sidebar (`/social`):

- **Analytics cards** — followers, posts, engagement rate per platform
- **Compose** — write once, Claude adapts for all 4 platforms
- **Platform preview** — see adapted content before posting
- **Schedule** — pick date/time for future posts
- **Scheduled queue** — view/cancel pending scheduled posts
- **Recent feed** — posted content with risk labels and approval actions
