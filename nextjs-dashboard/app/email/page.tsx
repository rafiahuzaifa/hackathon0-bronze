'use client';
import { useState, useEffect } from 'react';
import { Mail, RefreshCw, Send, Reply, AlertCircle, CheckCircle, Inbox, Clock, Tag } from 'lucide-react';

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface EmailItem {
  id: string;
  from: string;
  subject: string;
  intent: string;
  risk: string;
  received_at: string;
  preview: string;
  status: string;
  auto_reply?: string;
}

const MOCK_EMAILS: EmailItem[] = [
  { id: 'e1', from: 'ahmed@techcorp.io',    subject: 'Partnership Proposal — Q2 2026',          intent: 'partnership',  risk: 'high',   received_at: new Date(Date.now()-5*60000).toISOString(),    preview: 'Hi, we would like to explore a strategic partnership with your company...', status: 'needs_approval', auto_reply: 'Thank you for reaching out. We will review your proposal and get back to you within 2 business days.' },
  { id: 'e2', from: 'billing@stripe.com',   subject: 'Invoice #INV-2026-0312 — $450.00',        intent: 'invoice',      risk: 'low',    received_at: new Date(Date.now()-30*60000).toISOString(),   preview: 'Your invoice for March 2026 is ready. Amount due: $450.00', status: 'auto_replied' },
  { id: 'e3', from: 'sara@client.com',      subject: 'RE: Project Milestone Update',             intent: 'follow_up',    risk: 'medium', received_at: new Date(Date.now()-2*3600000).toISOString(),  preview: 'Just following up on the milestone deliverables discussed last week...', status: 'needs_approval', auto_reply: 'Hi Sara, I have reviewed the milestone status. I will send a detailed update by EOD.' },
  { id: 'e4', from: 'support@aws.com',      subject: 'Your AWS bill is ready',                   intent: 'invoice',      risk: 'low',    received_at: new Date(Date.now()-5*3600000).toISOString(),  preview: 'Your AWS bill for February 2026: $128.34', status: 'auto_replied' },
  { id: 'e5', from: 'hr@recruiting.io',     subject: 'Developer Role — Interested?',             intent: 'recruitment',  risk: 'low',    received_at: new Date(Date.now()-24*3600000).toISOString(), preview: 'We came across your profile and think you would be a great fit...', status: 'done' },
  { id: 'e6', from: 'ceo@bigclient.com',    subject: 'Urgent: Contract Renewal Discussion',      intent: 'contract',     risk: 'high',   received_at: new Date(Date.now()-2*86400000).toISOString(), preview: 'Our current contract expires next month. Let us schedule a call...', status: 'needs_approval', auto_reply: 'Thank you for flagging this. I will have our contracts team reach out within 24 hours.' },
];

const INTENT_COLORS: Record<string, { color: string; bg: string }> = {
  partnership: { color: '#a78bfa', bg: 'rgba(167,139,250,0.15)' },
  invoice:     { color: '#34d399', bg: 'rgba(52,211,153,0.15)'  },
  follow_up:   { color: '#60a5fa', bg: 'rgba(96,165,250,0.15)'  },
  recruitment: { color: '#64748b', bg: 'rgba(100,116,139,0.15)' },
  contract:    { color: '#f59e0b', bg: 'rgba(245,158,11,0.15)'  },
  support:     { color: '#fb923c', bg: 'rgba(251,146,60,0.15)'  },
};

const RISK_COLORS: Record<string, string> = { low: '#34d399', medium: '#f59e0b', high: '#f87171' };

function fmtRelative(iso: string) {
  const d = Date.now() - new Date(iso).getTime();
  if (d < 60000) return 'just now';
  if (d < 3600000) return `${Math.floor(d/60000)}m ago`;
  if (d < 86400000) return `${Math.floor(d/3600000)}h ago`;
  return `${Math.floor(d/86400000)}d ago`;
}

export default function EmailPage() {
  const [emails, setEmails] = useState<EmailItem[]>(MOCK_EMAILS);
  const [selected, setSelected] = useState<EmailItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [approving, setApproving] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all'|'needs_approval'|'auto_replied'|'done'>('all');

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${BASE}/api/tasks`);
      if (res.ok) {
        const tasks = await res.json();
        const emailTasks = tasks.filter((t: { filename: string }) => t.filename.startsWith('EMAIL_'));
        if (emailTasks.length) {
          // Map to EmailItem shape
          setEmails(emailTasks.map((t: { filename: string; status: string; created_at: string; content_preview: string }) => ({
            id: t.filename, from: 'unknown@source.com', subject: t.filename.replace('EMAIL_','').replace('.md',''),
            intent: 'general', risk: 'medium', received_at: t.created_at,
            preview: t.content_preview, status: t.status,
          })));
        }
      }
    } catch { /* use mock */ } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const approve = async (email: EmailItem) => {
    setApproving(email.id);
    try {
      await fetch(`${BASE}/api/approvals/${email.id}/approve`, { method: 'POST' });
      setEmails(prev => prev.map(e => e.id === email.id ? { ...e, status: 'done' } : e));
      if (selected?.id === email.id) setSelected({ ...email, status: 'done' });
    } catch { /* ignore */ } finally { setApproving(null); }
  };

  const filtered = filter === 'all' ? emails : emails.filter(e => e.status === filter);
  const counts = { needs_approval: emails.filter(e=>e.status==='needs_approval').length, auto_replied: emails.filter(e=>e.status==='auto_replied').length, done: emails.filter(e=>e.status==='done').length };

  return (
    <div className="animate-fade-in h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold" style={{ color: '#f1f5f9' }}>Email Manager</h1>
          <p className="text-sm" style={{ color: '#64748b' }}>Gmail watcher · Claude intent detection · auto-reply</p>
        </div>
        <button onClick={load} disabled={loading} className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm" style={{ background: '#1e2035', color: '#94a3b8', border: '1px solid #2a2d45' }}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {/* Stat chips */}
      <div className="flex gap-2 mb-4 flex-wrap">
        {([['all','All',null],['needs_approval','Needs Approval','#f59e0b'],['auto_replied','Auto-Replied','#34d399'],['done','Done','#60a5fa']] as const).map(([k,label,color]) => (
          <button key={k} onClick={() => setFilter(k)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all"
            style={{ background: filter===k ? (color ? `${color}20` : '#1e2035') : '#0f1020', color: filter===k ? (color || '#f1f5f9') : '#475569', border: `1px solid ${filter===k ? (color ? `${color}40` : '#3b82f6') : '#1e2035'}` }}>
            {label}
            {k !== 'all' && <span className="ml-1 px-1.5 py-0.5 rounded-full text-xs" style={{ background: 'rgba(255,255,255,0.08)' }}>{counts[k as keyof typeof counts]}</span>}
          </button>
        ))}
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4" style={{ height: 'calc(100vh - 220px)' }}>
        {/* Email list */}
        <div className="lg:col-span-2 overflow-y-auto rounded-xl" style={{ background: '#0f1020', border: '1px solid #1e2035' }}>
          {filtered.map(email => {
            const ic = INTENT_COLORS[email.intent] || INTENT_COLORS.support;
            const isSelected = selected?.id === email.id;
            return (
              <div key={email.id} onClick={() => setSelected(email)} className="p-4 cursor-pointer transition-colors border-b"
                style={{ background: isSelected ? '#13141f' : 'transparent', borderColor: '#1e2035', borderLeft: isSelected ? '3px solid #3b82f6' : '3px solid transparent' }}>
                <div className="flex items-start justify-between gap-2 mb-1">
                  <span className="text-xs font-medium truncate" style={{ color: '#94a3b8' }}>{email.from}</span>
                  <span className="text-xs flex-shrink-0" style={{ color: '#374151' }}>{fmtRelative(email.received_at)}</span>
                </div>
                <div className="text-sm font-semibold mb-1.5 line-clamp-1" style={{ color: '#f1f5f9' }}>{email.subject}</div>
                <div className="flex items-center gap-2">
                  <span className="text-xs px-1.5 py-0.5 rounded-full" style={{ color: ic.color, background: ic.bg }}>{email.intent}</span>
                  <span className="text-xs font-semibold" style={{ color: RISK_COLORS[email.risk] }}>{email.risk}</span>
                  {email.status === 'needs_approval' && <span className="ml-auto text-xs" style={{ color: '#f59e0b' }}>⏳ approval</span>}
                  {email.status === 'auto_replied' && <span className="ml-auto text-xs" style={{ color: '#34d399' }}>✓ replied</span>}
                  {email.status === 'done' && <span className="ml-auto text-xs" style={{ color: '#60a5fa' }}>✓ done</span>}
                </div>
              </div>
            );
          })}
          {filtered.length === 0 && (
            <div className="flex flex-col items-center justify-center h-40" style={{ color: '#374151' }}>
              <Inbox size={28} className="mb-2 opacity-30" />
              <p className="text-sm">No emails</p>
            </div>
          )}
        </div>

        {/* Email detail */}
        <div className="lg:col-span-3 rounded-xl overflow-hidden flex flex-col" style={{ background: '#0f1020', border: '1px solid #1e2035' }}>
          {selected ? (
            <>
              <div className="p-5 border-b" style={{ borderColor: '#1e2035' }}>
                <div className="flex items-start justify-between gap-3 mb-3">
                  <h2 className="text-base font-bold" style={{ color: '#f1f5f9' }}>{selected.subject}</h2>
                  <span className="text-xs font-semibold px-2 py-1 rounded-full flex-shrink-0"
                    style={{ color: RISK_COLORS[selected.risk], background: `${RISK_COLORS[selected.risk]}20` }}>
                    {selected.risk} risk
                  </span>
                </div>
                <div className="flex items-center gap-4 text-xs" style={{ color: '#64748b' }}>
                  <span className="flex items-center gap-1"><Mail size={12} />{selected.from}</span>
                  <span className="flex items-center gap-1"><Clock size={12} />{fmtRelative(selected.received_at)}</span>
                  <span className="flex items-center gap-1"><Tag size={12} />{selected.intent}</span>
                </div>
              </div>
              <div className="p-5 flex-1 overflow-y-auto space-y-4">
                <div>
                  <p className="text-xs font-semibold mb-2" style={{ color: '#475569' }}>ORIGINAL MESSAGE</p>
                  <div className="rounded-lg p-4 text-sm leading-relaxed" style={{ background: '#0a0b14', color: '#94a3b8', border: '1px solid #1e2035' }}>
                    {selected.preview}
                  </div>
                </div>
                {selected.auto_reply && (
                  <div>
                    <p className="text-xs font-semibold mb-2 flex items-center gap-1" style={{ color: '#a78bfa' }}>
                      <Reply size={12} /> CLAUDE AUTO-REPLY DRAFT
                    </p>
                    <div className="rounded-lg p-4 text-sm leading-relaxed" style={{ background: 'rgba(167,139,250,0.05)', color: '#cbd5e1', border: '1px solid rgba(167,139,250,0.2)' }}>
                      {selected.auto_reply}
                    </div>
                  </div>
                )}
              </div>
              {selected.status === 'needs_approval' && (
                <div className="p-4 border-t flex gap-2" style={{ borderColor: '#1e2035' }}>
                  <button onClick={() => approve(selected)} disabled={approving === selected.id}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold"
                    style={{ background: 'linear-gradient(135deg,#3b82f6,#7c3aed)', color: '#fff' }}>
                    {approving === selected.id ? <RefreshCw size={14} className="animate-spin" /> : <CheckCircle size={14} />}
                    Approve & Send
                  </button>
                  <button onClick={() => { setEmails(prev => prev.map(e => e.id === selected.id ? {...e, status:'done'} : e)); setSelected(s => s ? {...s, status:'done'} : s); }}
                    className="px-4 py-2 rounded-lg text-sm font-semibold" style={{ background: '#1a1b2e', color: '#f87171', border: '1px solid rgba(248,113,113,0.2)' }}>
                    Reject
                  </button>
                </div>
              )}
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-full" style={{ color: '#374151' }}>
              <Mail size={40} className="mb-3 opacity-20" />
              <p className="text-sm">Select an email to view</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
