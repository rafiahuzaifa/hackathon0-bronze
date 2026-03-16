'use client';
import { useState } from 'react';
import { Webhook, RefreshCw, CheckCircle, XCircle, Clock, Zap, ChevronDown, ChevronRight } from 'lucide-react';

interface WebhookEvent { id: string; source: string; event: string; payload_preview: string; received_at: string; status: 'processed'|'failed'|'pending'; retries: number; }

const MOCK_EVENTS: WebhookEvent[] = [
  { id: 'wh1', source: 'stripe',  event: 'payment_intent.succeeded', payload_preview: '{"amount":4500,"currency":"usd","customer":"cus_abc123"}', received_at: new Date(Date.now()-2*60000).toISOString(),   status: 'processed', retries: 0 },
  { id: 'wh2', source: 'github',  event: 'push',                      payload_preview: '{"ref":"refs/heads/main","commits":[{"message":"feat: add social page"}]}', received_at: new Date(Date.now()-15*60000).toISOString(), status: 'processed', retries: 0 },
  { id: 'wh3', source: 'stripe',  event: 'customer.subscription.updated', payload_preview: '{"plan":"pro","status":"active","amount":2900}', received_at: new Date(Date.now()-30*60000).toISOString(), status: 'processed', retries: 0 },
  { id: 'wh4', source: 'zapier',  event: 'form_submission',           payload_preview: '{"name":"John Doe","email":"john@example.com","message":"Interested in partnership"}', received_at: new Date(Date.now()-2*3600000).toISOString(),  status: 'failed',    retries: 3 },
  { id: 'wh5', source: 'github',  event: 'pull_request.opened',       payload_preview: '{"title":"Fix auth bug","user":"dev123","base":"main"}',        received_at: new Date(Date.now()-5*3600000).toISOString(),  status: 'processed', retries: 0 },
  { id: 'wh6', source: 'custom',  event: 'new_lead',                  payload_preview: '{"company":"BigCorp","contact":"ceo@bigcorp.com","budget":"$50k"}',received_at: new Date(Date.now()-6*3600000).toISOString(),  status: 'pending',   retries: 0 },
];

const SOURCE_COLORS: Record<string,{color:string;bg:string}> = {
  stripe:  {color:'#818cf8',bg:'rgba(129,140,248,0.15)'},
  github:  {color:'#94a3b8',bg:'rgba(148,163,184,0.15)'},
  zapier:  {color:'#f97316',bg:'rgba(249,115,22,0.15)'},
  custom:  {color:'#34d399',bg:'rgba(52,211,153,0.15)'},
};

function fmtTime(iso: string) {
  const d = Date.now()-new Date(iso).getTime();
  if (d<3600000) return `${Math.floor(d/60000)}m ago`;
  if (d<86400000) return `${Math.floor(d/3600000)}h ago`;
  return new Date(iso).toLocaleDateString();
}

export default function WebhooksPage() {
  const [events, setEvents] = useState(MOCK_EVENTS);
  const [expanded, setExpanded] = useState<string|null>(null);
  const [filter, setFilter] = useState<'all'|'processed'|'failed'|'pending'>('all');

  const retry = (id: string) => setEvents(prev => prev.map(e => e.id===id ? {...e, status:'processed', retries: e.retries} : e));
  const filtered = filter==='all' ? events : events.filter(e=>e.status===filter);
  const counts = { processed: events.filter(e=>e.status==='processed').length, failed: events.filter(e=>e.status==='failed').length, pending: events.filter(e=>e.status==='pending').length };

  return (
    <div className="animate-fade-in max-w-4xl space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{color:'#f1f5f9'}}>Webhook Manager</h1>
          <p className="text-sm" style={{color:'#64748b'}}>Incoming events · Stripe · GitHub · Zapier · Custom</p>
        </div>
        <div className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-full" style={{background:'rgba(59,130,246,0.1)',color:'#60a5fa',border:'1px solid rgba(59,130,246,0.2)'}}>
          <Zap size={12}/> Listening on /webhooks/in
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        {[['Processed', counts.processed,'#34d399'],['Failed', counts.failed,'#f87171'],['Pending', counts.pending,'#f59e0b']].map(([label,count,color])=>(
          <div key={String(label)} className="rounded-xl p-4 text-center" style={{background:'#0f1020',border:'1px solid #1e2035'}}>
            <div className="text-2xl font-bold mb-1" style={{color:String(color)}}>{count}</div>
            <div className="text-xs" style={{color:'#64748b'}}>{label}</div>
          </div>
        ))}
      </div>

      {/* Filter */}
      <div className="flex gap-2">
        {(['all','processed','failed','pending'] as const).map(k=>(
          <button key={k} onClick={()=>setFilter(k)} className="px-3 py-1.5 rounded-full text-xs font-semibold capitalize transition-all"
            style={{background:filter===k?'rgba(59,130,246,0.2)':'#0f1020',color:filter===k?'#60a5fa':'#475569',border:`1px solid ${filter===k?'rgba(59,130,246,0.4)':'#1e2035'}`}}>
            {k}
          </button>
        ))}
      </div>

      {/* Events */}
      <div className="rounded-xl overflow-hidden" style={{background:'#0f1020',border:'1px solid #1e2035'}}>
        {filtered.map((ev,i) => {
          const sc = SOURCE_COLORS[ev.source]||SOURCE_COLORS.custom;
          const isExp = expanded===ev.id;
          return (
            <div key={ev.id} className={i>0?'border-t':''} style={{borderColor:'#1e2035'}}>
              <div className="flex items-center gap-3 p-4 cursor-pointer hover:bg-[#13141f] transition-colors"
                onClick={()=>setExpanded(isExp?null:ev.id)}>
                {ev.status==='processed' && <CheckCircle size={16} style={{color:'#34d399',flexShrink:0}}/>}
                {ev.status==='failed'    && <XCircle    size={16} style={{color:'#f87171',flexShrink:0}}/>}
                {ev.status==='pending'   && <Clock      size={16} style={{color:'#f59e0b',flexShrink:0}}/>}
                <span className="text-xs px-2 py-0.5 rounded-full flex-shrink-0" style={{color:sc.color,background:sc.bg}}>{ev.source}</span>
                <span className="text-sm font-medium flex-1 truncate" style={{color:'#e2e8f0'}}>{ev.event}</span>
                <span className="text-xs flex-shrink-0" style={{color:'#475569'}}>{fmtTime(ev.received_at)}</span>
                {ev.retries>0 && <span className="text-xs px-1.5 py-0.5 rounded" style={{background:'rgba(248,113,113,0.1)',color:'#f87171'}}>{ev.retries} retries</span>}
                {isExp ? <ChevronDown size={14} style={{color:'#475569'}}/> : <ChevronRight size={14} style={{color:'#475569'}}/>}
              </div>
              {isExp && (
                <div className="px-4 pb-4">
                  <pre className="rounded-lg p-3 text-xs overflow-x-auto" style={{background:'#0a0b14',color:'#94a3b8',border:'1px solid #1e2035'}}>
                    {JSON.stringify(JSON.parse(ev.payload_preview), null, 2)}
                  </pre>
                  {ev.status==='failed' && (
                    <button onClick={()=>retry(ev.id)} className="mt-2 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold"
                      style={{background:'rgba(59,130,246,0.15)',color:'#60a5fa',border:'1px solid rgba(59,130,246,0.3)'}}>
                      <RefreshCw size={12}/> Retry
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
