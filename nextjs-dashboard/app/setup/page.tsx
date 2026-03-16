'use client';
import { useState, useEffect } from 'react';
import {
  Settings, Save, RefreshCw, CheckCircle, XCircle, AlertCircle,
  Eye, EyeOff, Linkedin, Twitter, Facebook, Instagram,
  Mail, MessageCircle, Building2, Zap, ExternalLink
} from 'lucide-react';

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ─── Types ────────────────────────────────────────────────────────────────────
interface Creds { [key: string]: string }
interface StatusMap { [platform: string]: 'ok' | 'error' | 'unconfigured' | 'checking' }

// ─── Platform sections ────────────────────────────────────────────────────────
const PLATFORMS = [
  {
    id: 'claude', label: 'Claude AI (Core)', Icon: Zap, color: '#a78bfa',
    docsUrl: 'https://console.anthropic.com/api-keys',
    fields: [{ key: 'ANTHROPIC_API_KEY', label: 'API Key', placeholder: 'sk-ant-...', secret: true }],
    note: 'Required for all AI features — content generation, risk assessment, email replies.',
  },
  {
    id: 'gmail', label: 'Gmail', Icon: Mail, color: '#ea4335',
    docsUrl: 'https://console.cloud.google.com/apis/credentials',
    fields: [
      { key: 'GMAIL_CLIENT_ID',     label: 'Client ID',     placeholder: '...apps.googleusercontent.com', secret: false },
      { key: 'GMAIL_CLIENT_SECRET', label: 'Client Secret', placeholder: 'GOCSPX-...',                     secret: true  },
    ],
    note: 'Enable Gmail API in Google Cloud Console → OAuth 2.0 Client ID (Desktop app).',
  },
  {
    id: 'linkedin', label: 'LinkedIn', Icon: Linkedin, color: '#0A66C2',
    docsUrl: 'https://developer.linkedin.com/apps',
    fields: [
      { key: 'LINKEDIN_CLIENT_ID',     label: 'Client ID',     placeholder: '86xxxxx',   secret: false },
      { key: 'LINKEDIN_CLIENT_SECRET', label: 'Client Secret', placeholder: 'xxxxxxxx',  secret: true  },
      { key: 'LINKEDIN_ACCESS_TOKEN',  label: 'Access Token',  placeholder: 'AQV...',    secret: true  },
      { key: 'LINKEDIN_REFRESH_TOKEN', label: 'Refresh Token', placeholder: 'AQW...',    secret: true  },
    ],
    note: 'Create LinkedIn Developer App → add "Share on LinkedIn" product → OAuth 2.0.',
  },
  {
    id: 'twitter', label: 'Twitter / X', Icon: Twitter, color: '#1DA1F2',
    docsUrl: 'https://developer.twitter.com/en/portal/dashboard',
    fields: [
      { key: 'TWITTER_API_KEY',              label: 'API Key',          placeholder: 'xxxxxxxx', secret: false },
      { key: 'TWITTER_API_SECRET',           label: 'API Secret',       placeholder: 'xxxxxxxx', secret: true  },
      { key: 'TWITTER_ACCESS_TOKEN',         label: 'Access Token',     placeholder: '...-....',  secret: true  },
      { key: 'TWITTER_ACCESS_TOKEN_SECRET',  label: 'Access Secret',    placeholder: 'xxxxxxxx', secret: true  },
      { key: 'TWITTER_BEARER_TOKEN',         label: 'Bearer Token',     placeholder: 'AAAA...',  secret: true  },
    ],
    note: 'Create Developer App → Enable Read & Write permissions → Generate all tokens.',
  },
  {
    id: 'facebook', label: 'Facebook', Icon: Facebook, color: '#1877F2',
    docsUrl: 'https://developers.facebook.com/apps',
    fields: [
      { key: 'FACEBOOK_APP_ID',           label: 'App ID',           placeholder: '123456789',     secret: false },
      { key: 'FACEBOOK_APP_SECRET',       label: 'App Secret',       placeholder: 'xxxxxxxx',      secret: true  },
      { key: 'FACEBOOK_PAGE_ACCESS_TOKEN',label: 'Page Access Token',placeholder: 'EAA...',         secret: true  },
      { key: 'FACEBOOK_PAGE_ID',          label: 'Page ID',          placeholder: '987654321',     secret: false },
    ],
    note: 'Create Business App → Add Pages API product → Generate Page Access Token from Graph API Explorer.',
  },
  {
    id: 'instagram', label: 'Instagram', Icon: Instagram, color: '#E1306C',
    docsUrl: 'https://developers.facebook.com/apps',
    fields: [
      { key: 'INSTAGRAM_ACCESS_TOKEN', label: 'Access Token', placeholder: 'EAA... (same as Facebook long-lived)', secret: true  },
      { key: 'INSTAGRAM_ACCOUNT_ID',   label: 'Account ID',   placeholder: '111222333444',                          secret: false },
    ],
    note: 'Requires Instagram Business/Creator account linked to a Facebook Page.',
  },
  {
    id: 'whatsapp', label: 'WhatsApp (Playwright)', Icon: MessageCircle, color: '#25D366',
    docsUrl: 'https://web.whatsapp.com',
    fields: [
      { key: 'WHATSAPP_SESSION_PATH', label: 'Session Path', placeholder: './sessions/whatsapp', secret: false },
    ],
    note: 'WhatsApp uses browser automation. First run will show a QR code — scan with your phone.',
  },
  {
    id: 'bank', label: 'Bank Monitor', Icon: Building2, color: '#10b981',
    docsUrl: '',
    fields: [
      { key: 'BANK_CURRENCY',           label: 'Currency',       placeholder: 'PKR',      secret: false },
      { key: 'BANK_ANOMALY_THRESHOLD',  label: 'Alert Threshold',placeholder: '50000',    secret: false },
    ],
    note: 'Upload your bank CSV statements from the Bank Monitor page. No external API needed.',
  },
];

// ─── Component ────────────────────────────────────────────────────────────────
export default function SetupPage() {
  const [creds, setCreds] = useState<Creds>({});
  const [status, setStatus] = useState<StatusMap>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [showSecrets, setShowSecrets] = useState<{ [k: string]: boolean }>({});
  const [globalToast, setGlobalToast] = useState<{ msg: string; ok: boolean } | null>(null);
  const [dryRun, setDryRun] = useState(true);

  // Load existing config
  useEffect(() => {
    fetch(`${BASE}/api/system/credentials`)
      .then(r => r.json())
      .then(d => { setCreds(d.credentials || {}); setDryRun(d.dry_run ?? true); })
      .catch(() => {});

    fetch(`${BASE}/api/system/status`)
      .then(r => r.json())
      .then(d => setStatus(d))
      .catch(() => {});
  }, []);

  function toast(msg: string, ok: boolean) {
    setGlobalToast({ msg, ok });
    setTimeout(() => setGlobalToast(null), 3000);
  }

  async function savePlatform(platformId: string, fields: { key: string }[]) {
    setSaving(platformId);
    const payload: Creds = {};
    fields.forEach(f => { if (creds[f.key]) payload[f.key] = creds[f.key]; });
    try {
      const res = await fetch(`${BASE}/api/system/credentials`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.ok) { toast(`${platformId} credentials saved ✓`, true); }
      else { toast('Save failed — is the backend running?', false); }
    } catch {
      toast('Backend not reachable. Start: cd ai_employee && python -m uvicorn api.server:app --reload', false);
    } finally { setSaving(null); }
  }

  async function testConnection(platformId: string) {
    setTesting(platformId);
    setStatus(s => ({ ...s, [platformId]: 'checking' }));
    try {
      const res = await fetch(`${BASE}/api/system/test/${platformId}`, { method: 'POST' });
      const d = await res.json();
      setStatus(s => ({ ...s, [platformId]: d.ok ? 'ok' : 'error' }));
      toast(d.ok ? `${platformId} connected ✓` : `${platformId}: ${d.error || 'failed'}`, d.ok);
    } catch {
      setStatus(s => ({ ...s, [platformId]: 'error' }));
      toast('Cannot reach backend', false);
    } finally { setTesting(null); }
  }

  function statusIcon(id: string) {
    const s = status[id];
    if (s === 'ok')          return <CheckCircle size={14} style={{ color: '#34d399' }} />;
    if (s === 'error')       return <XCircle     size={14} style={{ color: '#f87171' }} />;
    if (s === 'checking')    return <RefreshCw   size={14} className="animate-spin" style={{ color: '#60a5fa' }} />;
    return <AlertCircle size={14} style={{ color: '#475569' }} />;
  }

  return (
    <div className="animate-fade-in max-w-3xl space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: '#f1f5f9' }}>Setup & Credentials</h1>
          <p className="text-sm mt-0.5" style={{ color: '#64748b' }}>
            Configure real API credentials so the AI Employee can act on your behalf
          </p>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold"
          style={dryRun
            ? { background: 'rgba(20,184,166,0.1)', color: '#2dd4bf', border: '1px solid rgba(20,184,166,0.25)' }
            : { background: 'rgba(239,68,68,0.1)', color: '#f87171', border: '1px solid rgba(239,68,68,0.3)' }}>
          {dryRun ? '🛡️ DEMO MODE' : '🔴 LIVE MODE'}
        </div>
      </div>

      {/* Backend status banner */}
      <div className="rounded-xl p-4 space-y-2" style={{ background: '#0f1020', border: '1px solid #1e2035' }}>
        <p className="text-xs font-semibold" style={{ color: '#475569' }}>BACKEND SETUP</p>
        <div className="bg-black/30 rounded-lg p-3 font-mono text-xs space-y-1" style={{ color: '#34d399' }}>
          <div style={{ color: '#475569' }}># Install dependencies</div>
          <div>pip install -r ai_employee/requirements.txt</div>
          <div style={{ color: '#475569' }}># Install Playwright browser (for WhatsApp)</div>
          <div>playwright install chromium</div>
          <div style={{ color: '#475569' }}># Start the API server</div>
          <div>cd ai_employee &amp;&amp; uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload</div>
        </div>
        <p className="text-xs" style={{ color: '#64748b' }}>
          Then set <code className="text-purple-400">NEXT_PUBLIC_API_URL=http://YOUR_SERVER_IP:8000</code> in Vercel environment variables.
        </p>
      </div>

      {/* Platform cards */}
      {PLATFORMS.map(platform => {
        const { id, label, Icon, color, docsUrl, fields, note } = platform;
        const isSaving  = saving  === id;
        const isTesting = testing === id;
        const s = status[id];

        return (
          <div key={id} className="rounded-xl overflow-hidden" style={{ background: '#0f1020', border: '1px solid #1e2035' }}>
            {/* Card header */}
            <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: '#1e2035' }}>
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: `${color}20` }}>
                  <Icon size={16} style={{ color }} />
                </div>
                <span className="text-sm font-bold" style={{ color: '#f1f5f9' }}>{label}</span>
                {statusIcon(id)}
              </div>
              <div className="flex items-center gap-2">
                {docsUrl && (
                  <a href={docsUrl} target="_blank" rel="noreferrer"
                    className="flex items-center gap-1 text-xs px-2 py-1 rounded transition-colors hover:bg-[#1e2035]"
                    style={{ color: '#475569' }}>
                    <ExternalLink size={11} /> Docs
                  </a>
                )}
                <button onClick={() => testConnection(id)} disabled={isTesting}
                  className="text-xs px-3 py-1 rounded-lg disabled:opacity-40"
                  style={{ background: '#1a1b2e', color: '#60a5fa', border: '1px solid rgba(96,165,250,0.2)' }}>
                  {isTesting ? <RefreshCw size={11} className="animate-spin inline" /> : 'Test'}
                </button>
              </div>
            </div>

            {/* Fields */}
            <div className="p-5 space-y-3">
              {fields.map(field => (
                <div key={field.key}>
                  <label className="block text-xs font-medium mb-1" style={{ color: '#64748b' }}>
                    {field.label}
                  </label>
                  <div className="relative">
                    <input
                      type={field.secret && !showSecrets[field.key] ? 'password' : 'text'}
                      value={creds[field.key] || ''}
                      onChange={e => setCreds(c => ({ ...c, [field.key]: e.target.value }))}
                      placeholder={field.placeholder}
                      className="w-full rounded-lg px-3 py-2 text-sm outline-none pr-9"
                      style={{ background: '#0a0b14', color: '#e2e8f0', border: '1px solid #2a2d45' }}
                    />
                    {field.secret && (
                      <button
                        onClick={() => setShowSecrets(s => ({ ...s, [field.key]: !s[field.key] }))}
                        className="absolute right-2 top-1/2 -translate-y-1/2"
                        style={{ color: '#475569' }}>
                        {showSecrets[field.key] ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    )}
                  </div>
                </div>
              ))}

              <p className="text-xs" style={{ color: '#374151' }}>{note}</p>

              <button
                onClick={() => savePlatform(id, fields)}
                disabled={isSaving}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold disabled:opacity-40"
                style={{ background: `${color}20`, color, border: `1px solid ${color}40` }}>
                {isSaving ? <RefreshCw size={13} className="animate-spin" /> : <Save size={13} />}
                Save {label}
              </button>
            </div>

            {/* Connection status */}
            {s && s !== 'checking' && (
              <div className="px-5 pb-4">
                <div className="flex items-center gap-2 text-xs px-3 py-2 rounded-lg"
                  style={s === 'ok'
                    ? { background: 'rgba(52,211,153,0.08)', color: '#34d399', border: '1px solid rgba(52,211,153,0.2)' }
                    : { background: 'rgba(248,113,113,0.08)', color: '#f87171', border: '1px solid rgba(248,113,113,0.2)' }}>
                  {s === 'ok' ? <CheckCircle size={12} /> : <XCircle size={12} />}
                  {s === 'ok' ? `${label} connected and ready` : `${label} connection failed — check credentials`}
                </div>
              </div>
            )}
          </div>
        );
      })}

      {/* Global toast */}
      {globalToast && (
        <div className="fixed bottom-5 right-5 z-50 flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium shadow-xl"
          style={globalToast.ok
            ? { background: '#0f1020', border: '1px solid #34d399', color: '#34d399' }
            : { background: '#0f1020', border: '1px solid #f87171', color: '#f87171' }}>
          {globalToast.ok ? <CheckCircle size={14} /> : <AlertCircle size={14} />}
          {globalToast.msg}
        </div>
      )}
    </div>
  );
}
