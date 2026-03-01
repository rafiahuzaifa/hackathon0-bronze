import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiFetch } from '../App';

export default function LogsViewer() {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter,  setFilter]  = useState('');
  const [level,   setLevel]   = useState('ALL');
  const bottomRef = useRef(null);

  const fetchLogs = useCallback(async () => {
    try {
      const r = await apiFetch('/api/logs?n=200');
      setEntries(r.entries || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchLogs(); const t = setInterval(fetchLogs, 10000); return () => clearInterval(t); }, [fetchLogs]);

  const filtered = entries.filter(e => {
    const text = JSON.stringify(e).toLowerCase();
    const matchText  = !filter || text.includes(filter.toLowerCase());
    const matchLevel = level === 'ALL' || (e.level === level);
    return matchText && matchLevel;
  });

  if (loading) return <p className="loading"><span className="spinner" /> Loading logs…</p>;

  return (
    <div className="card">
      <div className="card-title">📄 Logs Viewer — /Logs/*.jsonl</div>

      <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
        <input
          placeholder="Filter logs…"
          value={filter} onChange={e => setFilter(e.target.value)}
          style={{ flex: 1 }}
        />
        <select value={level} onChange={e => setLevel(e.target.value)} style={{ width: 100 }}>
          <option value="ALL">All levels</option>
          <option value="INFO">INFO</option>
          <option value="WARN">WARN</option>
          <option value="ERROR">ERROR</option>
        </select>
        <button className="btn btn-sm" style={{ background: 'var(--border)', color: 'var(--text)' }}
                onClick={fetchLogs}>↻ Refresh</button>
      </div>

      <div style={{ maxHeight: '65vh', overflowY: 'auto', fontFamily: 'var(--mono)' }}>
        {filtered.length === 0 ? (
          <p style={{ color: 'var(--muted)', padding: '20px 0', textAlign: 'center' }}>No log entries found.</p>
        ) : (
          filtered.map((e, i) => (
            <div key={i} className="log-entry">
              <span className="log-ts">{(e.ts || '').slice(0, 19)}</span>
              <span className={`log-${e.level || 'INFO'}`}>[{e.level || 'LOG'}]</span>
              <span className="log-msg">
                {e.event ? `${e.event}: ` : ''}{e.message || e.msg || e.raw || JSON.stringify(e)}
              </span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      <p style={{ color: 'var(--muted)', fontSize: 11, marginTop: 10 }}>
        Showing {filtered.length} / {entries.length} entries. Auto-refreshes every 10s.
      </p>
    </div>
  );
}
