'use client';
import { useState } from 'react';
import { MessageCircle, Send, RefreshCw, CheckCircle, User, Clock } from 'lucide-react';

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Message { id: string; text: string; from: 'them' | 'me'; time: string; }
interface Contact { id: string; name: string; phone: string; intent: string; risk: string; last_message: string; last_time: string; unread: number; messages: Message[]; status: string; auto_reply?: string; }

const MOCK_CONTACTS: Contact[] = [
  { id: 'c1', name: 'Ali Hassan', phone: '+92-300-1234567', intent: 'partnership', risk: 'high', last_message: 'Are you available for a call tomorrow?', last_time: new Date(Date.now()-3*60000).toISOString(), unread: 2, status: 'needs_approval',
    auto_reply: 'Hi Ali! Thank you for reaching out. I would be happy to schedule a call. Please suggest a time that works for you.',
    messages: [
      { id: 'm1', text: 'Hello! I wanted to discuss a potential collaboration.', from: 'them', time: new Date(Date.now()-10*60000).toISOString() },
      { id: 'm2', text: 'We are working on an AI project and think your expertise would be valuable.', from: 'them', time: new Date(Date.now()-8*60000).toISOString() },
      { id: 'm3', text: 'Are you available for a call tomorrow?', from: 'them', time: new Date(Date.now()-3*60000).toISOString() },
    ]},
  { id: 'c2', name: 'Sara Ahmed', phone: '+92-321-9876543', intent: 'support', risk: 'low', last_message: 'Invoice sent, please confirm receipt.', last_time: new Date(Date.now()-30*60000).toISOString(), unread: 0, status: 'auto_replied',
    auto_reply: 'Hi Sara! Invoice received, thank you. I will process it within 24 hours.',
    messages: [
      { id: 'm4', text: 'Hi, sending over the invoice for last month.', from: 'them', time: new Date(Date.now()-35*60000).toISOString() },
      { id: 'm5', text: 'Invoice sent, please confirm receipt.', from: 'them', time: new Date(Date.now()-30*60000).toISOString() },
      { id: 'm6', text: 'Hi Sara! Invoice received, thank you. I will process it within 24 hours.', from: 'me', time: new Date(Date.now()-28*60000).toISOString() },
    ]},
  { id: 'c3', name: 'TechCorp Support', phone: '+1-800-TECHCORP', intent: 'support', risk: 'low', last_message: 'Your ticket #4521 has been resolved.', last_time: new Date(Date.now()-2*3600000).toISOString(), unread: 0, status: 'done',
    messages: [
      { id: 'm7', text: 'Your ticket #4521 has been resolved.', from: 'them', time: new Date(Date.now()-2*3600000).toISOString() },
    ]},
];

const INTENT_COLORS: Record<string, { color: string; bg: string }> = {
  partnership: { color: '#a78bfa', bg: 'rgba(167,139,250,0.15)' },
  support:     { color: '#60a5fa', bg: 'rgba(96,165,250,0.15)'  },
  invoice:     { color: '#34d399', bg: 'rgba(52,211,153,0.15)'  },
};
const RISK_COLORS: Record<string,string> = { low:'#34d399', medium:'#f59e0b', high:'#f87171' };

function fmtRelative(iso: string) {
  const d = Date.now()-new Date(iso).getTime();
  if (d<60000) return 'now';
  if (d<3600000) return `${Math.floor(d/60000)}m`;
  if (d<86400000) return `${Math.floor(d/3600000)}h`;
  return `${Math.floor(d/86400000)}d`;
}

export default function WhatsAppPage() {
  const [contacts, setContacts] = useState<Contact[]>(MOCK_CONTACTS);
  const [selected, setSelected] = useState<Contact | null>(MOCK_CONTACTS[0]);
  const [reply, setReply] = useState('');
  const [sending, setSending] = useState(false);

  const send = async () => {
    if (!reply.trim() || !selected) return;
    setSending(true);
    const msg: Message = { id: Date.now().toString(), text: reply, from: 'me', time: new Date().toISOString() };
    setContacts(prev => prev.map(c => c.id === selected.id ? { ...c, messages: [...c.messages, msg], last_message: reply, last_time: msg.time, status: 'done' } : c));
    setSelected(s => s ? { ...s, messages: [...s.messages, msg], status: 'done' } : s);
    setReply('');
    setSending(false);
  };

  const approve = async (contact: Contact) => {
    if (!contact.auto_reply) return;
    const msg: Message = { id: Date.now().toString(), text: contact.auto_reply, from: 'me', time: new Date().toISOString() };
    setContacts(prev => prev.map(c => c.id === contact.id ? { ...c, messages: [...c.messages, msg], status: 'done', unread: 0 } : c));
    setSelected(s => s?.id === contact.id ? { ...s, messages: [...s.messages, msg], status: 'done' } : s);
    try { await fetch(`${BASE}/api/approvals/${contact.id}/approve`, { method: 'POST' }); } catch { /* ignore */ }
  };

  return (
    <div className="animate-fade-in h-full flex flex-col">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold" style={{ color: '#f1f5f9' }}>WhatsApp Manager</h1>
          <p className="text-sm" style={{ color: '#64748b' }}>Playwright automation · Claude intent detection · approval flow</p>
        </div>
        <div className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-full" style={{ background: 'rgba(37,211,102,0.1)', color: '#25D366', border: '1px solid rgba(37,211,102,0.2)' }}>
          <span className="w-2 h-2 rounded-full bg-[#25D366] animate-pulse" /> Connected
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 flex-1 min-h-0">
        {/* Contacts */}
        <div className="lg:col-span-2 overflow-y-auto rounded-xl" style={{ background: '#0f1020', border: '1px solid #1e2035' }}>
          {contacts.map(c => {
            const ic = INTENT_COLORS[c.intent] || INTENT_COLORS.support;
            return (
              <div key={c.id} onClick={() => { setSelected(c); setContacts(prev => prev.map(x => x.id === c.id ? {...x, unread:0} : x)); }}
                className="p-4 cursor-pointer border-b transition-colors"
                style={{ background: selected?.id===c.id ? '#13141f' : 'transparent', borderColor: '#1e2035', borderLeft: selected?.id===c.id ? '3px solid #25D366' : '3px solid transparent' }}>
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full flex items-center justify-center font-bold text-white flex-shrink-0 text-sm"
                    style={{ background: 'linear-gradient(135deg,#25D366,#128C7E)' }}>{c.name[0]}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-semibold" style={{ color: '#f1f5f9' }}>{c.name}</span>
                      <span className="text-xs" style={{ color: '#374151' }}>{fmtRelative(c.last_time)}</span>
                    </div>
                    <p className="text-xs truncate mt-0.5" style={{ color: '#64748b' }}>{c.last_message}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs px-1.5 py-0.5 rounded-full" style={{ color: ic.color, background: ic.bg }}>{c.intent}</span>
                      <span className="text-xs font-semibold" style={{ color: RISK_COLORS[c.risk] }}>{c.risk}</span>
                      {c.unread > 0 && <span className="ml-auto w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold text-white" style={{ background: '#25D366' }}>{c.unread}</span>}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Chat */}
        <div className="lg:col-span-3 rounded-xl flex flex-col min-h-0" style={{ background: '#0f1020', border: '1px solid #1e2035' }}>
          {selected ? (
            <>
              {/* Chat header */}
              <div className="px-4 py-3 border-b flex items-center gap-3" style={{ borderColor: '#1e2035' }}>
                <div className="w-9 h-9 rounded-full flex items-center justify-center font-bold text-white text-sm flex-shrink-0"
                  style={{ background: 'linear-gradient(135deg,#25D366,#128C7E)' }}>{selected.name[0]}</div>
                <div>
                  <div className="text-sm font-bold" style={{ color: '#f1f5f9' }}>{selected.name}</div>
                  <div className="text-xs" style={{ color: '#64748b' }}>{selected.phone}</div>
                </div>
                <span className="ml-auto text-xs font-semibold px-2 py-0.5 rounded-full"
                  style={{ color: RISK_COLORS[selected.risk], background: `${RISK_COLORS[selected.risk]}20` }}>
                  {selected.risk} risk
                </span>
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {selected.messages.map(msg => (
                  <div key={msg.id} className={`flex ${msg.from==='me' ? 'justify-end' : 'justify-start'}`}>
                    <div className="max-w-xs px-3 py-2 rounded-xl text-sm"
                      style={{ background: msg.from==='me' ? '#25D366' : '#1e2035', color: msg.from==='me' ? '#fff' : '#cbd5e1' }}>
                      {msg.text}
                      <div className="text-xs mt-1 opacity-60">{fmtRelative(msg.time)}</div>
                    </div>
                  </div>
                ))}
              </div>

              {/* Auto-reply approval */}
              {selected.status === 'needs_approval' && selected.auto_reply && (
                <div className="mx-4 mb-3 p-3 rounded-lg" style={{ background: 'rgba(167,139,250,0.08)', border: '1px solid rgba(167,139,250,0.2)' }}>
                  <p className="text-xs font-semibold mb-1" style={{ color: '#a78bfa' }}>Claude Draft Reply</p>
                  <p className="text-xs mb-2" style={{ color: '#94a3b8' }}>{selected.auto_reply}</p>
                  <button onClick={() => approve(selected)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold"
                    style={{ background: '#25D366', color: '#fff' }}>
                    <CheckCircle size={12} /> Approve & Send
                  </button>
                </div>
              )}

              {/* Input */}
              <div className="p-3 border-t flex gap-2" style={{ borderColor: '#1e2035' }}>
                <input value={reply} onChange={e => setReply(e.target.value)} onKeyDown={e => e.key==='Enter' && send()}
                  placeholder="Type a message..." className="flex-1 rounded-xl px-3 py-2 text-sm outline-none"
                  style={{ background: '#0a0b14', color: '#e2e8f0', border: '1px solid #2a2d45' }} />
                <button onClick={send} disabled={sending || !reply.trim()}
                  className="w-9 h-9 rounded-xl flex items-center justify-center disabled:opacity-40"
                  style={{ background: '#25D366' }}>
                  {sending ? <RefreshCw size={14} className="animate-spin text-white" /> : <Send size={14} className="text-white" />}
                </button>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center h-full" style={{ color: '#374151' }}>
              <MessageCircle size={40} className="mb-3 opacity-20" />
              <p className="text-sm">Select a contact</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
