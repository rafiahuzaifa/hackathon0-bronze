'use client';
import { useState, useRef } from 'react';
import { Building2, Upload, AlertTriangle, CheckCircle, TrendingUp, TrendingDown, DollarSign, RefreshCw } from 'lucide-react';

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Transaction { id: string; date: string; description: string; amount: number; type: 'income'|'expense'; flags: string[]; }

const MOCK_TXN: Transaction[] = [
  { id: 't1',  date: '2026-03-15', description: 'CLIENT RETAINER - TECHCORP',     amount:  50000, type: 'income',  flags: [] },
  { id: 't2',  date: '2026-03-14', description: 'AWS SERVICES',                   amount: -12800, type: 'expense', flags: [] },
  { id: 't3',  date: '2026-03-14', description: 'ROUND PAYMENT - UNKNOWN VENDOR', amount: -100000, type: 'expense', flags: ['ROUND_AMOUNT_FLAG','UNKNOWN_VENDOR_FLAG'] },
  { id: 't4',  date: '2026-03-13', description: 'PROJECT PAYMENT - SARA DESIGN',  amount:  25000, type: 'income',  flags: [] },
  { id: 't5',  date: '2026-03-12', description: 'ANTHROPIC API CREDITS',           amount:  -6000, type: 'expense', flags: [] },
  { id: 't6',  date: '2026-03-12', description: 'LARGE TRANSFER - UNIDENTIFIED',  amount: -500000, type: 'expense', flags: ['HIGH_VALUE_FLAG','UNKNOWN_VENDOR_FLAG'] },
  { id: 't7',  date: '2026-03-11', description: 'CONSULTING FEE - BIGCORP',       amount: 100000, type: 'income',  flags: [] },
  { id: 't8',  date: '2026-03-10', description: 'CONTRACTOR PAYMENT',             amount: -18000, type: 'expense', flags: [] },
  { id: 't9',  date: '2026-03-09', description: 'STRIPE PAYOUT',                  amount:  37500, type: 'income',  flags: [] },
  { id: 't10', date: '2026-03-08', description: 'DUPLICATE CHARGE - AWS',         amount: -12800, type: 'expense', flags: ['DUPLICATE_FLAG'] },
];

const FLAG_LABELS: Record<string,{label:string;color:string}> = {
  ROUND_AMOUNT_FLAG:  {label:'Round Amount',   color:'#f59e0b'},
  HIGH_VALUE_FLAG:    {label:'High Value',     color:'#f87171'},
  UNKNOWN_VENDOR_FLAG:{label:'Unknown Vendor', color:'#fb923c'},
  DUPLICATE_FLAG:     {label:'Duplicate',      color:'#a78bfa'},
};

function fmtPKR(n: number) {
  return `PKR ${Math.abs(n).toLocaleString()}`;
}

export default function BankPage() {
  const [txns, setTxns] = useState<Transaction[]>(MOCK_TXN);
  const [uploading, setUploading] = useState(false);
  const [filter, setFilter] = useState<'all'|'flagged'>('all');
  const fileRef = useRef<HTMLInputElement>(null);

  const income   = txns.filter(t=>t.type==='income').reduce((s,t)=>s+t.amount,0);
  const expenses = txns.filter(t=>t.type==='expense').reduce((s,t)=>s+Math.abs(t.amount),0);
  const flagged  = txns.filter(t=>t.flags.length>0);
  const filtered = filter==='flagged' ? flagged : txns;

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    const form = new FormData(); form.append('file', file);
    try {
      const res = await fetch(`${BASE}/api/bank/upload`, { method:'POST', body:form });
      if (res.ok) { const d = await res.json(); if (d.transactions) setTxns(d.transactions); }
    } catch { /* use mock */ } finally { setUploading(false); }
  };

  return (
    <div className="animate-fade-in max-w-5xl space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{color:'#f1f5f9'}}>Bank Monitor</h1>
          <p className="text-sm" style={{color:'#64748b'}}>Upload CSV · Anomaly detection · Audit trail</p>
        </div>
        <button onClick={()=>fileRef.current?.click()} disabled={uploading}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold"
          style={{background:'linear-gradient(135deg,#3b82f6,#7c3aed)',color:'#fff'}}>
          {uploading ? <RefreshCw size={14} className="animate-spin"/> : <Upload size={14}/>}
          Upload CSV
        </button>
        <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={handleUpload}/>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          {label:'Total Income',   value:fmtPKR(income),   icon:TrendingUp,   color:'#34d399'},
          {label:'Total Expenses', value:fmtPKR(expenses), icon:TrendingDown, color:'#f87171'},
          {label:'Net Balance',    value:fmtPKR(income-expenses), icon:DollarSign, color:income>expenses?'#34d399':'#f87171'},
          {label:'Flagged',        value:String(flagged.length)+' transactions', icon:AlertTriangle, color:'#f59e0b'},
        ].map(({label,value,icon:Icon,color})=>(
          <div key={label} className="rounded-xl p-4" style={{background:'#0f1020',border:'1px solid #1e2035'}}>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{background:`${color}20`}}>
                <Icon size={14} style={{color}}/>
              </div>
              <span className="text-xs" style={{color:'#64748b'}}>{label}</span>
            </div>
            <div className="text-base font-bold truncate" style={{color}}>{value}</div>
          </div>
        ))}
      </div>

      {/* Anomaly banner */}
      {flagged.length > 0 && (
        <div className="rounded-xl p-4 flex items-start gap-3" style={{background:'rgba(245,158,11,0.08)',border:'1px solid rgba(245,158,11,0.25)'}}>
          <AlertTriangle size={18} style={{color:'#f59e0b',flexShrink:0,marginTop:2}}/>
          <div>
            <p className="text-sm font-semibold" style={{color:'#f59e0b'}}>{flagged.length} anomalies detected</p>
            <p className="text-xs mt-0.5" style={{color:'#92400e'}}>Review flagged transactions below. Files moved to vault/Needs_Action/ for AI review.</p>
          </div>
        </div>
      )}

      {/* Filter */}
      <div className="flex gap-2">
        {(['all','flagged'] as const).map(k=>(
          <button key={k} onClick={()=>setFilter(k)} className="px-3 py-1.5 rounded-full text-xs font-semibold capitalize"
            style={{background:filter===k?'rgba(59,130,246,0.2)':'#0f1020',color:filter===k?'#60a5fa':'#475569',border:`1px solid ${filter===k?'rgba(59,130,246,0.4)':'#1e2035'}`}}>
            {k==='all'?`All (${txns.length})`:`Flagged (${flagged.length})`}
          </button>
        ))}
      </div>

      {/* Transactions table */}
      <div className="rounded-xl overflow-hidden" style={{background:'#0f1020',border:'1px solid #1e2035'}}>
        <table className="w-full text-xs">
          <thead>
            <tr style={{borderBottom:'1px solid #1e2035'}}>
              {['Date','Description','Amount','Flags','Status'].map(h=>(
                <th key={h} className="text-left px-4 py-3 font-semibold" style={{color:'#475569'}}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((t,i)=>(
              <tr key={t.id} className="border-t hover:bg-[#13141f] transition-colors" style={{borderColor:'#1e2035'}}>
                <td className="px-4 py-3" style={{color:'#64748b'}}>{t.date}</td>
                <td className="px-4 py-3 max-w-xs">
                  <span className="truncate block" style={{color:'#e2e8f0'}}>{t.description}</span>
                </td>
                <td className="px-4 py-3 font-mono font-semibold" style={{color:t.type==='income'?'#34d399':'#f87171'}}>
                  {t.type==='income'?'+':'-'}{fmtPKR(t.amount)}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {t.flags.map(f=>(
                      <span key={f} className="px-1.5 py-0.5 rounded text-xs" style={{color:FLAG_LABELS[f]?.color||'#64748b',background:`${FLAG_LABELS[f]?.color||'#64748b'}15`}}>
                        {FLAG_LABELS[f]?.label||f}
                      </span>
                    ))}
                    {t.flags.length===0 && <span style={{color:'#374151'}}>—</span>}
                  </div>
                </td>
                <td className="px-4 py-3">
                  {t.flags.length>0
                    ? <span className="flex items-center gap-1 text-xs" style={{color:'#f59e0b'}}><AlertTriangle size={11}/>Flagged</span>
                    : <span className="flex items-center gap-1 text-xs" style={{color:'#34d399'}}><CheckCircle size={11}/>Clean</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
