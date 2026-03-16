'use client';
import { useState, useRef } from 'react';
import { Search, Loader2, FileText, Mail, MessageCircle, Share2, Building2, Zap, Clock } from 'lucide-react';

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface SearchResult { id: string; title: string; type: string; preview: string; date: string; path: string; relevance: number; }

const TYPE_ICONS: Record<string, { icon: React.ElementType; color: string }> = {
  email:    { icon: Mail,           color: '#3b82f6' },
  whatsapp: { icon: MessageCircle,  color: '#25D366' },
  social:   { icon: Share2,         color: '#a78bfa' },
  bank:     { icon: Building2,      color: '#10b981' },
  vault:    { icon: FileText,       color: '#f59e0b' },
  task:     { icon: Zap,            color: '#f97316' },
};

const SAMPLE_RESULTS: SearchResult[] = [
  { id: 'r1', title: 'Partnership email from TechCorp',      type: 'email',    preview: 'Hi, we would like to explore a strategic partnership with your AI Employee system...', date: '2026-03-15', path: 'vault/Done/EMAIL_20260315_092341.md',     relevance: 97 },
  { id: 'r2', title: 'LinkedIn Q1 Results Post',             type: 'social',   preview: 'Excited to share our Q1 results — 34% growth in client base and 47 automated tasks per week...', date: '2026-03-14', path: 'vault/Done/SOCIAL_LINKEDIN_20260314.md', relevance: 92 },
  { id: 'r3', title: 'WhatsApp: Ali Hassan partnership',     type: 'whatsapp', preview: 'Hello! I wanted to discuss a potential collaboration on your AI platform...', date: '2026-03-13', path: 'vault/Needs_Action/WA_ali_20260313.md',   relevance: 88 },
  { id: 'r4', title: 'Bank anomaly — unknown vendor',        type: 'bank',     preview: 'ROUND_AMOUNT_FLAG, UNKNOWN_VENDOR_FLAG detected on PKR 100,000 transaction to UNKNOWN VENDOR', date: '2026-03-14', path: 'vault/Needs_Action/BANK_ALERT_20260314.md', relevance: 85 },
  { id: 'r5', title: 'Company Handbook',                     type: 'vault',    preview: 'Operating policies, communication guidelines, approval thresholds, and escalation rules for AI Employee...', date: '2026-03-01', path: 'vault/Company_Handbook.md',           relevance: 78 },
  { id: 'r6', title: 'CEO Briefing Week Mar 10–16',          type: 'vault',    preview: 'Strong week — 47 tasks completed, 2 high-risk escalations handled, revenue up 34%...', date: '2026-03-16', path: 'vault/Briefings/CEO_Briefing_20260316.md', relevance: 75 },
];

const SUGGESTIONS = ['partnership email', 'bank anomaly', 'high risk approval', 'Q1 report', 'LinkedIn post', 'WhatsApp Ali'];

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const search = async (q = query) => {
    if (!q.trim()) return;
    setQuery(q);
    setLoading(true);
    setSearched(true);
    try {
      const res = await fetch(`${BASE}/api/search?q=${encodeURIComponent(q)}`);
      if (res.ok) { const d = await res.json(); setResults(d.results || []); }
      else { throw new Error(); }
    } catch {
      // Show filtered mock results
      const lower = q.toLowerCase();
      setResults(SAMPLE_RESULTS.filter(r =>
        r.title.toLowerCase().includes(lower) || r.preview.toLowerCase().includes(lower) || r.type.includes(lower)
      ).length ? SAMPLE_RESULTS.filter(r =>
        r.title.toLowerCase().includes(lower) || r.preview.toLowerCase().includes(lower)
      ) : SAMPLE_RESULTS.slice(0, 4));
    } finally { setLoading(false); }
  };

  return (
    <div className="animate-fade-in max-w-3xl mx-auto space-y-5">
      <div className="text-center mb-8">
        <div className="w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-4"
          style={{background:'linear-gradient(135deg,rgba(59,130,246,0.2),rgba(124,58,237,0.2))',border:'1px solid rgba(59,130,246,0.3)'}}>
          <Search size={22} style={{color:'#60a5fa'}}/>
        </div>
        <h1 className="text-xl font-bold mb-1" style={{color:'#f1f5f9'}}>AI Vault Search</h1>
        <p className="text-sm" style={{color:'#64748b'}}>Search across emails, social posts, bank records, and all vault documents</p>
      </div>

      {/* Search box */}
      <div className="relative">
        <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2" style={{color:'#475569'}}/>
        <input
          ref={inputRef}
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key==='Enter' && search()}
          placeholder="Search vault documents, emails, tasks, social posts..."
          className="w-full rounded-xl pl-11 pr-16 py-3.5 text-sm outline-none"
          style={{background:'#0f1020',color:'#e2e8f0',border:'1px solid #2a2d45'}}
          autoFocus
        />
        <button onClick={() => search()} disabled={loading || !query.trim()}
          className="absolute right-2 top-1/2 -translate-y-1/2 px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-40"
          style={{background:'linear-gradient(135deg,#3b82f6,#7c3aed)',color:'#fff'}}>
          {loading ? <Loader2 size={13} className="animate-spin"/> : 'Search'}
        </button>
      </div>

      {/* Suggestions */}
      {!searched && (
        <div>
          <p className="text-xs mb-2" style={{color:'#374151'}}>Try searching for:</p>
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map(s => (
              <button key={s} onClick={() => search(s)}
                className="px-3 py-1.5 rounded-full text-xs transition-colors hover:bg-[#1e2035]"
                style={{background:'#0f1020',color:'#64748b',border:'1px solid #1e2035'}}>
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Results */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 size={24} className="animate-spin" style={{color:'#3b82f6'}}/>
          <span className="ml-3 text-sm" style={{color:'#64748b'}}>Searching vault with Claude RAG...</span>
        </div>
      )}

      {searched && !loading && (
        <div className="space-y-2">
          <p className="text-xs mb-3" style={{color:'#475569'}}>{results.length} results for &quot;{query}&quot;</p>
          {results.map(r => {
            const tc = TYPE_ICONS[r.type] || TYPE_ICONS.vault;
            const Icon = tc.icon;
            return (
              <div key={r.id} className="rounded-xl p-4 hover:bg-[#13141f] transition-colors cursor-pointer"
                style={{background:'#0f1020',border:'1px solid #1e2035'}}>
                <div className="flex items-start gap-3">
                  <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
                    style={{background:`${tc.color}20`}}>
                    <Icon size={13} style={{color:tc.color}}/>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-semibold" style={{color:'#f1f5f9'}}>{r.title}</span>
                      <span className="text-xs px-1.5 py-0.5 rounded-full" style={{color:tc.color,background:`${tc.color}15`}}>{r.type}</span>
                      <span className="ml-auto text-xs flex-shrink-0" style={{color:'#374151'}}>
                        <Clock size={10} className="inline mr-0.5"/>{r.date}
                      </span>
                    </div>
                    <p className="text-xs leading-relaxed line-clamp-2 mb-2" style={{color:'#64748b'}}>{r.preview}</p>
                    <div className="flex items-center gap-3">
                      <span className="text-xs font-mono truncate" style={{color:'#374151'}}>{r.path}</span>
                      <span className="text-xs font-semibold flex-shrink-0" style={{color:r.relevance>90?'#34d399':r.relevance>75?'#f59e0b':'#64748b'}}>
                        {r.relevance}% match
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
          {results.length === 0 && (
            <div className="text-center py-10" style={{color:'#374151'}}>
              <Search size={28} className="mx-auto mb-2 opacity-20"/>
              <p className="text-sm">No results found for &quot;{query}&quot;</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
