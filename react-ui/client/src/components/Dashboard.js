import React, { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '../App';

export default function Dashboard() {
  const [data,         setData]         = useState(null);
  const [pending,      setPending]       = useState([]);
  const [loading,      setLoading]       = useState(true);
  const [auditRunning, setAuditRunning]  = useState(false);
  const [auditOutput,  setAuditOutput]   = useState('');
  const [error,        setError]         = useState('');

  const fetchAll = useCallback(async () => {
    try {
      const [dash, pend] = await Promise.all([
        apiFetch('/api/dashboard'),
        apiFetch('/api/pending'),
      ]);
      setData(dash);
      setPending(pend);
      setError('');
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); const t = setInterval(fetchAll, 30000); return () => clearInterval(t); }, [fetchAll]);

  async function runAudit() {
    setAuditRunning(true);
    setAuditOutput('Running orchestrator…');
    try {
      const r = await apiFetch('/api/audit', { method: 'POST' });
      setAuditOutput(r.output || '(no output)');
    } catch (e) {
      setAuditOutput('Error: ' + e.message);
    } finally {
      setAuditRunning(false);
      fetchAll();
    }
  }

  if (loading) return <p className="loading"><span className="spinner" /> Loading dashboard…</p>;
  if (error)   return <p style={{ color: 'var(--red)', padding: '20px 0' }}>Error: {error}</p>;

  return (
    <>
      <div className="stats">
        <div className="stat">
          <div className="stat-num">{pending.length}</div>
          <div className="stat-lbl">Pending Approval</div>
        </div>
        <div className="stat">
          <div className="stat-num" style={{ fontSize: 13, paddingTop: 5 }}>
            {new Date().toLocaleTimeString()}
          </div>
          <div className="stat-lbl">Live</div>
        </div>
      </div>

      <div className="grid2">
        {/* Dashboard.md */}
        <div>
          <div className="card">
            <div className="card-title">📊 Vault Dashboard</div>
            <div className="md-body" dangerouslySetInnerHTML={{ __html: data?.dashboard?.html }} />
          </div>

          {data?.goals?.html && (
            <div className="card">
              <div className="card-title">🎯 Business Goals</div>
              <div className="md-body" dangerouslySetInnerHTML={{ __html: data.goals.html }} />
            </div>
          )}
        </div>

        {/* Pending + Audit */}
        <div>
          {pending.length > 0 && (
            <div className="card">
              <div className="card-title">📋 Pending Approval ({pending.length})</div>
              {pending.slice(0, 5).map(item => (
                <div key={item.filename} className="pending-item">
                  <div className="pending-meta">
                    <div className="pending-name">
                      <span className={`pill pill-${item.category}`}>{item.category}</span>
                      {item.filename}
                    </div>
                    <div className="pending-body">{item.body.slice(0, 120)}</div>
                  </div>
                </div>
              ))}
              {pending.length > 5 && (
                <p style={{ color: 'var(--muted)', fontSize: 12, marginTop: 8 }}>
                  +{pending.length - 5} more — <a href="/approvals">View all →</a>
                </p>
              )}
            </div>
          )}

          <div className="card">
            <div className="card-title">⚡ Manual Audit</div>
            <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 12 }}>
              Run the orchestrator immediately to process new tasks.
            </p>
            <button className="btn btn-primary" onClick={runAudit} disabled={auditRunning}>
              {auditRunning ? <><span className="spinner" /> Running…</> : '▶ Run Audit'}
            </button>
            {auditOutput && <pre className="audit-output">{auditOutput}</pre>}
          </div>
        </div>
      </div>
    </>
  );
}
