'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Send, Calendar, BarChart2, Clock, Trash2, CheckCircle,
  AlertCircle, RefreshCw, Image as ImageIcon, Linkedin,
  Twitter, Facebook, Instagram, Globe, Zap, TrendingUp,
  Users, Eye, Heart, MessageCircle, X
} from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

interface ScheduledPost {
  filename: string;
  platform: string;
  scheduled_time: string;
  content_preview: string;
  recurring: string;
  status: string;
}

interface Analytics {
  platform: string;
  followers?: number;
  following?: number;
  post_count?: number;
  reach?: number;
  engagement_rate?: number;
  name?: string;
}

interface FeedItem {
  id: string;
  platform: string;
  content_preview: string;
  created_at: string;
  status: string;
  risk?: string;
  result?: string;
}

interface PostResult {
  status: string;
  result?: Record<string, unknown>;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const PLATFORM_CONFIG = {
  linkedin:  { label: 'LinkedIn',  color: '#0A66C2', bg: 'rgba(10,102,194,0.15)',  Icon: Linkedin,  maxChars: 3000 },
  twitter:   { label: 'Twitter/X', color: '#1DA1F2', bg: 'rgba(29,161,242,0.15)',  Icon: Twitter,   maxChars: 280  },
  facebook:  { label: 'Facebook',  color: '#1877F2', bg: 'rgba(24,119,242,0.15)',  Icon: Facebook,  maxChars: 63206},
  instagram: { label: 'Instagram', color: '#E1306C', bg: 'rgba(225,48,108,0.15)',  Icon: Instagram, maxChars: 2200 },
} as const;

type Platform = keyof typeof PLATFORM_CONFIG;

const MOCK_ANALYTICS: Analytics[] = [
  { platform: 'linkedin',  followers: 2840, following: 312,  post_count: 47,  engagement_rate: 4.2, name: 'AI Employee' },
  { platform: 'twitter',   followers: 1205, following: 489,  post_count: 183, engagement_rate: 2.8, name: '@ai_employee' },
  { platform: 'facebook',  followers: 3412, following: 0,    post_count: 62,  engagement_rate: 3.1, name: 'AI Employee Page' },
  { platform: 'instagram', followers: 5610, following: 821,  post_count: 94,  engagement_rate: 6.7, name: '@ai_employee' },
];

const MOCK_FEED: FeedItem[] = [
  { id: 'f1', platform: 'linkedin',  content_preview: 'Excited to share our Q1 results — 34% growth in client base...', created_at: new Date(Date.now() - 2*3600000).toISOString(), status: 'done',             risk: 'low'    },
  { id: 'f2', platform: 'twitter',   content_preview: 'Thread: 5 ways AI is transforming small business operations 🧵', created_at: new Date(Date.now() - 5*3600000).toISOString(), status: 'done',             risk: 'low'    },
  { id: 'f3', platform: 'instagram', content_preview: 'Behind the scenes of our AI Employee dashboard build 🚀',       created_at: new Date(Date.now() - 8*3600000).toISOString(), status: 'pending_approval', risk: 'medium' },
  { id: 'f4', platform: 'facebook',  content_preview: 'New partnership announcement coming soon — stay tuned!',         created_at: new Date(Date.now() - 24*3600000).toISOString(),status: 'done',             risk: 'low'    },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json() as Promise<T>;
}

function fmtRelative(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60000) return 'just now';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return `${Math.floor(diff / 86400000)}d ago`;
}

function fmtNum(n?: number) {
  if (n == null) return '—';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
  return String(n);
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function PlatformBadge({ platform, size = 14 }: { platform: string; size?: number }) {
  const cfg = PLATFORM_CONFIG[platform as Platform];
  if (!cfg) return <span style={{ color: '#64748b', fontSize: 12 }}>{platform}</span>;
  const { Icon, color, label } = cfg;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full"
          style={{ color, background: PLATFORM_CONFIG[platform as Platform].bg }}>
      <Icon size={size - 2} />
      {label}
    </span>
  );
}

function RiskBadge({ risk }: { risk?: string }) {
  if (!risk) return null;
  const map: Record<string, { color: string; bg: string }> = {
    low:    { color: '#34d399', bg: 'rgba(52,211,153,0.15)' },
    medium: { color: '#f59e0b', bg: 'rgba(245,158,11,0.15)' },
    high:   { color: '#f87171', bg: 'rgba(248,113,113,0.15)' },
  };
  const s = map[risk] || map.medium;
  return (
    <span className="text-xs font-semibold px-1.5 py-0.5 rounded-full uppercase"
          style={{ color: s.color, background: s.bg }}>
      {risk}
    </span>
  );
}

function CharCounter({ text, max }: { text: string; max: number }) {
  const used = text.length;
  const pct = used / max;
  const color = pct > 0.9 ? '#f87171' : pct > 0.7 ? '#f59e0b' : '#64748b';
  return (
    <span className="text-xs font-mono" style={{ color }}>
      {used}/{max}
    </span>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function SocialPage() {
  // Compose state
  const [content, setContent] = useState('');
  const [selectedPlatforms, setSelectedPlatforms] = useState<Platform[]>(['linkedin', 'twitter']);
  const [imageUrl, setImageUrl] = useState('');
  const [scheduleMode, setScheduleMode] = useState(false);
  const [scheduleTime, setScheduleTime] = useState('');
  const [posting, setPosting] = useState(false);
  const [postResult, setPostResult] = useState<PostResult | null>(null);

  // Preview state
  const [previews, setPreviews] = useState<Record<string, string>>({});
  const [previewLoading, setPreviewLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Data state
  const [analytics, setAnalytics] = useState<Analytics[]>(MOCK_ANALYTICS);
  const [scheduled, setScheduled] = useState<ScheduledPost[]>([]);
  const [feed, setFeed] = useState<FeedItem[]>(MOCK_FEED);
  const [loadingData, setLoadingData] = useState(false);

  // ── Load data ──────────────────────────────────────────────────────────────

  const loadData = useCallback(async () => {
    setLoadingData(true);
    try {
      const [analyticsData, scheduledData, feedData] = await Promise.allSettled([
        apiFetch<Analytics[]>('/api/social/analytics'),
        apiFetch<ScheduledPost[]>('/api/social/scheduled'),
        apiFetch<FeedItem[]>('/api/social/feed'),
      ]);
      if (analyticsData.status === 'fulfilled') setAnalytics(analyticsData.value);
      if (scheduledData.status === 'fulfilled') setScheduled(scheduledData.value);
      if (feedData.status === 'fulfilled') setFeed(feedData.value.length ? feedData.value : MOCK_FEED);
    } catch {
      // Keep mock data on error
    } finally {
      setLoadingData(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  // ── Claude preview (debounced 1s) ──────────────────────────────────────────

  useEffect(() => {
    if (!content.trim()) { setPreviews({}); return; }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setPreviewLoading(true);
      // Build simple client-side previews (truncate to platform limits)
      const newPreviews: Record<string, string> = {};
      for (const p of selectedPlatforms) {
        const max = PLATFORM_CONFIG[p].maxChars;
        newPreviews[p] = content.length > max
          ? content.slice(0, max - 3) + '...'
          : content;
      }
      setPreviews(newPreviews);
      setPreviewLoading(false);
    }, 800);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [content, selectedPlatforms]);

  // ── Toggle platform ────────────────────────────────────────────────────────

  function togglePlatform(p: Platform) {
    setSelectedPlatforms(prev =>
      prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]
    );
  }

  // ── Post / Schedule ────────────────────────────────────────────────────────

  async function handlePost(schedule = false) {
    if (!content.trim() || selectedPlatforms.length === 0) return;
    setPosting(true);
    setPostResult(null);
    try {
      const body: Record<string, unknown> = {
        content,
        platforms: selectedPlatforms,
        ...(imageUrl ? { image_url: imageUrl } : {}),
        ...(schedule && scheduleTime ? { schedule_time: scheduleTime } : {}),
      };
      const result = await apiFetch<PostResult>('/api/social/post', {
        method: 'POST',
        body: JSON.stringify(body),
      });
      setPostResult(result);
      if (result.status === 'ok') {
        setContent('');
        setImageUrl('');
        setScheduleTime('');
        setScheduleMode(false);
        setTimeout(loadData, 1500);
      }
    } catch (e) {
      setPostResult({ status: 'error', result: { error: String(e) } });
    } finally {
      setPosting(false);
    }
  }

  // ── Cancel scheduled ───────────────────────────────────────────────────────

  async function cancelScheduled(filename: string) {
    try {
      await apiFetch(`/api/social/scheduled/${encodeURIComponent(filename)}`, { method: 'DELETE' });
      setScheduled(prev => prev.filter(p => p.filename !== filename));
    } catch { /* ignore */ }
  }

  // ── Approve feed item ──────────────────────────────────────────────────────

  async function approveFeedItem(id: string) {
    try {
      await apiFetch(`/api/social/approve/${id}`, { method: 'POST' });
      setFeed(prev => prev.map(f => f.id === id ? { ...f, status: 'approved' } : f));
    } catch { /* ignore */ }
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────────────────────

  return (
    <div className="animate-fade-in space-y-6 max-w-6xl">
      {/* ── Page header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: '#f1f5f9' }}>Social Media Command Center</h1>
          <p className="text-sm mt-0.5" style={{ color: '#64748b' }}>
            Claude-powered content • 4 platforms • Real-time preview
          </p>
        </div>
        <button onClick={loadData} disabled={loadingData}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors"
                style={{ background: '#1e2035', color: '#94a3b8', border: '1px solid #2a2d45' }}>
          <RefreshCw size={14} className={loadingData ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* ── Analytics cards ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {(analytics.length ? analytics : MOCK_ANALYTICS).map(a => {
          const cfg = PLATFORM_CONFIG[a.platform as Platform];
          if (!cfg) return null;
          const { Icon, color, bg, label } = cfg;
          return (
            <div key={a.platform} className="rounded-xl p-4 space-y-3"
                 style={{ background: '#0f1020', border: '1px solid #1e2035' }}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: bg }}>
                    <Icon size={14} style={{ color }} />
                  </div>
                  <span className="text-xs font-semibold" style={{ color: '#94a3b8' }}>{label}</span>
                </div>
                {a.engagement_rate && (
                  <span className="text-xs font-bold" style={{ color: '#34d399' }}>
                    {a.engagement_rate}%
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-2 text-center">
                <div>
                  <div className="text-base font-bold" style={{ color: '#f1f5f9' }}>{fmtNum(a.followers)}</div>
                  <div className="text-xs" style={{ color: '#475569' }}>Followers</div>
                </div>
                <div>
                  <div className="text-base font-bold" style={{ color: '#f1f5f9' }}>{fmtNum(a.post_count)}</div>
                  <div className="text-xs" style={{ color: '#475569' }}>Posts</div>
                </div>
              </div>
              {a.name && (
                <div className="text-xs truncate" style={{ color: '#475569' }}>{a.name}</div>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Main grid: Compose + Feed ── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">

        {/* ── Compose panel (3/5) ── */}
        <div className="lg:col-span-3 space-y-4">
          <div className="rounded-xl p-5 space-y-4"
               style={{ background: '#0f1020', border: '1px solid #1e2035' }}>
            <h2 className="text-sm font-bold" style={{ color: '#94a3b8' }}>
              COMPOSE POST
            </h2>

            {/* Platform toggles */}
            <div className="flex flex-wrap gap-2">
              {(Object.keys(PLATFORM_CONFIG) as Platform[]).map(p => {
                const { Icon, color, bg, label } = PLATFORM_CONFIG[p];
                const active = selectedPlatforms.includes(p);
                return (
                  <button key={p} onClick={() => togglePlatform(p)}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
                          style={{
                            background: active ? bg : '#1a1b2e',
                            color: active ? color : '#475569',
                            border: `1px solid ${active ? color + '40' : '#2a2d45'}`,
                          }}>
                    <Icon size={13} />
                    {label}
                  </button>
                );
              })}
              <button onClick={() => setSelectedPlatforms(Object.keys(PLATFORM_CONFIG) as Platform[])}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
                      style={{ background: '#1a1b2e', color: '#a78bfa', border: '1px solid rgba(167,139,250,0.3)' }}>
                <Globe size={13} />
                All
              </button>
            </div>

            {/* Text area */}
            <div className="relative">
              <textarea
                value={content}
                onChange={e => setContent(e.target.value)}
                placeholder="Write your post content here. Claude will adapt it per platform…"
                rows={6}
                className="w-full rounded-lg p-3 text-sm resize-none outline-none focus:ring-1"
                style={{
                  background: '#0a0b14',
                  color: '#e2e8f0',
                  border: '1px solid #2a2d45',
                  lineHeight: 1.6,
                  // @ts-expect-error CSS variable
                  '--tw-ring-color': '#3b82f6',
                }}
              />
              <div className="flex justify-end gap-3 mt-1.5">
                {selectedPlatforms.map(p => (
                  <CharCounter key={p} text={content} max={PLATFORM_CONFIG[p].maxChars} />
                ))}
              </div>
            </div>

            {/* Image URL */}
            <div className="flex items-center gap-2">
              <ImageIcon size={15} style={{ color: '#475569' }} />
              <input
                value={imageUrl}
                onChange={e => setImageUrl(e.target.value)}
                placeholder="Image URL (optional — must be publicly accessible)"
                className="flex-1 rounded-lg px-3 py-1.5 text-xs outline-none"
                style={{ background: '#0a0b14', color: '#e2e8f0', border: '1px solid #2a2d45' }}
              />
            </div>

            {/* Schedule toggle */}
            <div className="flex items-center gap-3">
              <button
                onClick={() => setScheduleMode(s => !s)}
                className="flex items-center gap-1.5 text-xs font-medium transition-colors"
                style={{ color: scheduleMode ? '#a78bfa' : '#475569' }}>
                <Clock size={13} />
                {scheduleMode ? 'Scheduling' : 'Schedule for later'}
              </button>
              {scheduleMode && (
                <input
                  type="datetime-local"
                  value={scheduleTime}
                  onChange={e => setScheduleTime(e.target.value)}
                  className="rounded-lg px-2 py-1 text-xs outline-none"
                  style={{ background: '#0a0b14', color: '#e2e8f0', border: '1px solid #2a2d45' }}
                />
              )}
            </div>

            {/* Action buttons */}
            <div className="flex gap-2 pt-1">
              <button
                onClick={() => handlePost(false)}
                disabled={posting || !content.trim() || selectedPlatforms.length === 0}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all disabled:opacity-40"
                style={{ background: 'linear-gradient(135deg, #3b82f6, #7c3aed)', color: '#fff' }}>
                {posting ? <RefreshCw size={14} className="animate-spin" /> : <Send size={14} />}
                Post Now
              </button>
              {scheduleMode && (
                <button
                  onClick={() => handlePost(true)}
                  disabled={posting || !content.trim() || !scheduleTime || selectedPlatforms.length === 0}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all disabled:opacity-40"
                  style={{ background: '#1a1b2e', color: '#a78bfa', border: '1px solid rgba(167,139,250,0.3)' }}>
                  <Calendar size={14} />
                  Schedule
                </button>
              )}
              {content && (
                <button onClick={() => { setContent(''); setPreviews({}); }}
                        className="ml-auto px-3 py-2 rounded-lg text-xs transition-colors"
                        style={{ color: '#475569', background: '#1a1b2e', border: '1px solid #2a2d45' }}>
                  Clear
                </button>
              )}
            </div>

            {/* Post result */}
            {postResult && (
              <div className="flex items-start gap-2 p-3 rounded-lg text-sm"
                   style={{
                     background: postResult.status === 'ok' ? 'rgba(52,211,153,0.1)' : 'rgba(248,113,113,0.1)',
                     border: `1px solid ${postResult.status === 'ok' ? 'rgba(52,211,153,0.3)' : 'rgba(248,113,113,0.3)'}`,
                     color: postResult.status === 'ok' ? '#34d399' : '#f87171',
                   }}>
                {postResult.status === 'ok'
                  ? <CheckCircle size={15} className="mt-0.5 flex-shrink-0" />
                  : <AlertCircle size={15} className="mt-0.5 flex-shrink-0" />}
                <span>
                  {postResult.status === 'ok'
                    ? 'Post submitted! Claude is adapting content per platform.'
                    : `Error: ${JSON.stringify(postResult.result)}`}
                </span>
              </div>
            )}
          </div>

          {/* ── Platform previews ── */}
          {Object.keys(previews).length > 0 && (
            <div className="rounded-xl p-5 space-y-3"
                 style={{ background: '#0f1020', border: '1px solid #1e2035' }}>
              <div className="flex items-center gap-2">
                <Zap size={14} style={{ color: '#a78bfa' }} />
                <h2 className="text-sm font-bold" style={{ color: '#94a3b8' }}>PLATFORM PREVIEW</h2>
                {previewLoading && <RefreshCw size={12} className="animate-spin ml-auto" style={{ color: '#475569' }} />}
              </div>
              {selectedPlatforms.map(p => {
                const { color, bg, Icon, label } = PLATFORM_CONFIG[p];
                const preview = previews[p];
                if (!preview) return null;
                return (
                  <div key={p} className="rounded-lg p-3 space-y-2"
                       style={{ background: '#0a0b14', border: `1px solid ${color}25` }}>
                    <div className="flex items-center gap-2">
                      <div className="w-6 h-6 rounded-md flex items-center justify-center" style={{ background: bg }}>
                        <Icon size={12} style={{ color }} />
                      </div>
                      <span className="text-xs font-semibold" style={{ color }}>{label}</span>
                      <CharCounter text={preview} max={PLATFORM_CONFIG[p].maxChars} />
                    </div>
                    <p className="text-sm leading-relaxed whitespace-pre-wrap" style={{ color: '#cbd5e1' }}>
                      {preview}
                    </p>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* ── Feed panel (2/5) ── */}
        <div className="lg:col-span-2 space-y-4">
          <div className="rounded-xl p-5 space-y-3"
               style={{ background: '#0f1020', border: '1px solid #1e2035' }}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <TrendingUp size={14} style={{ color: '#3b82f6' }} />
                <h2 className="text-sm font-bold" style={{ color: '#94a3b8' }}>RECENT POSTS</h2>
              </div>
              <span className="text-xs" style={{ color: '#475569' }}>{feed.length} posts</span>
            </div>

            <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
              {feed.map(item => (
                <div key={item.id} className="rounded-lg p-3 space-y-2"
                     style={{ background: '#0a0b14', border: '1px solid #1e2035' }}>
                  <div className="flex items-center gap-2 flex-wrap">
                    <PlatformBadge platform={item.platform} />
                    <RiskBadge risk={item.risk} />
                    {item.status === 'done' ? (
                      <span className="ml-auto text-xs font-medium" style={{ color: '#34d399' }}>✓ posted</span>
                    ) : item.status === 'pending_approval' ? (
                      <button onClick={() => approveFeedItem(item.id)}
                              className="ml-auto text-xs font-medium px-2 py-0.5 rounded transition-colors"
                              style={{ background: 'rgba(59,130,246,0.15)', color: '#60a5fa', border: '1px solid rgba(59,130,246,0.3)' }}>
                        Approve
                      </button>
                    ) : (
                      <span className="ml-auto text-xs" style={{ color: '#64748b' }}>{item.status}</span>
                    )}
                  </div>
                  <p className="text-xs leading-relaxed line-clamp-2" style={{ color: '#94a3b8' }}>
                    {item.content_preview}
                  </p>
                  <div className="flex items-center gap-3 text-xs" style={{ color: '#374151' }}>
                    <span>{fmtRelative(item.created_at)}</span>
                    {item.result && <span className="truncate">{item.result}</span>}
                  </div>
                </div>
              ))}
              {feed.length === 0 && (
                <div className="text-center py-8" style={{ color: '#374151' }}>
                  <MessageCircle size={28} className="mx-auto mb-2 opacity-30" />
                  <p className="text-sm">No posts yet</p>
                </div>
              )}
            </div>
          </div>

          {/* Platform stats mini */}
          <div className="rounded-xl p-4 space-y-2"
               style={{ background: '#0f1020', border: '1px solid #1e2035' }}>
            <div className="flex items-center gap-2 mb-3">
              <BarChart2 size={14} style={{ color: '#a78bfa' }} />
              <h2 className="text-sm font-bold" style={{ color: '#94a3b8' }}>ENGAGEMENT</h2>
            </div>
            {(analytics.length ? analytics : MOCK_ANALYTICS).map(a => {
              const cfg = PLATFORM_CONFIG[a.platform as Platform];
              if (!cfg) return null;
              const { color } = cfg;
              const rate = a.engagement_rate ?? 0;
              return (
                <div key={a.platform} className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <PlatformBadge platform={a.platform} size={11} />
                    <span style={{ color: '#94a3b8' }}>{rate}%</span>
                  </div>
                  <div className="h-1.5 rounded-full" style={{ background: '#1e2035' }}>
                    <div className="h-1.5 rounded-full transition-all duration-500"
                         style={{ width: `${Math.min(rate * 10, 100)}%`, background: color }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Scheduled posts table ── */}
      <div className="rounded-xl p-5 space-y-4"
           style={{ background: '#0f1020', border: '1px solid #1e2035' }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock size={14} style={{ color: '#f59e0b' }} />
            <h2 className="text-sm font-bold" style={{ color: '#94a3b8' }}>SCHEDULED QUEUE</h2>
          </div>
          <span className="text-xs px-2 py-0.5 rounded-full font-semibold"
                style={{ background: 'rgba(245,158,11,0.1)', color: '#f59e0b' }}>
            {scheduled.length} pending
          </span>
        </div>

        {scheduled.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr style={{ borderBottom: '1px solid #1e2035' }}>
                  {['Platform', 'Preview', 'Scheduled', 'Recurring', ''].map(h => (
                    <th key={h} className="text-left pb-2 pr-4 font-semibold" style={{ color: '#475569' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y" style={{ borderColor: '#1e2035' }}>
                {scheduled.map(post => (
                  <tr key={post.filename} className="hover:bg-[#0a0b14] transition-colors">
                    <td className="py-2 pr-4">
                      <PlatformBadge platform={post.platform} />
                    </td>
                    <td className="py-2 pr-4 max-w-xs">
                      <span className="line-clamp-1" style={{ color: '#94a3b8' }}>
                        {post.content_preview || '—'}
                      </span>
                    </td>
                    <td className="py-2 pr-4 whitespace-nowrap" style={{ color: '#64748b' }}>
                      {post.scheduled_time
                        ? new Date(post.scheduled_time).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
                        : '—'}
                    </td>
                    <td className="py-2 pr-4">
                      {post.recurring !== 'none' ? (
                        <span className="px-1.5 py-0.5 rounded text-xs"
                              style={{ background: 'rgba(167,139,250,0.1)', color: '#a78bfa' }}>
                          {post.recurring}
                        </span>
                      ) : <span style={{ color: '#374151' }}>—</span>}
                    </td>
                    <td className="py-2">
                      <button onClick={() => cancelScheduled(post.filename)}
                              className="p-1 rounded transition-colors hover:bg-red-900/20"
                              title="Cancel scheduled post">
                        <Trash2 size={13} style={{ color: '#475569' }} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-10" style={{ color: '#374151' }}>
            <Calendar size={32} className="mx-auto mb-2 opacity-30" />
            <p className="text-sm">No scheduled posts</p>
            <p className="text-xs mt-1" style={{ color: '#1e2035' }}>
              Use the compose area above to schedule posts
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
