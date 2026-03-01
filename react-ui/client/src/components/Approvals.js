import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiFetch } from '../App';

function PendingCard({ item, onApprove, onReject }) {
  const [leaving, setLeaving] = useState(false);
  const [busy,    setBusy]    = useState(false);

  function act(fn) {
    setBusy(true);
    setLeaving(true);
    setTimeout(() => fn(), 300);
  }

  return (
    <div className={`pending-item ${leaving ? 'leaving' : ''}`} data-file={item.filename}>
      <div className="pending-meta">
        <div className="pending-name">
          <span className={`pill pill-${item.category}`}>{item.category}</span>
          <strong>{item.filename}</strong>
        </div>
        <div style={{ fontSize: 11, color: 'var(--muted)', margin: '3px 0 6px' }}>
          Modified: {new Date(item.modified).toLocaleString()}
          {Object.entries(item.meta || {}).map(([k, v]) => (
            <span key={k}>&nbsp;|&nbsp;<strong>{k}</strong>: {v}</span>
          ))}
        </div>
        <div className="pending-body">{item.body}</div>
      </div>
      <div className="pending-actions">
        <button className="btn btn-approve btn-sm" disabled={busy} onClick={() => act(() => onApprove(item.filename))}>
          ✓ Approve
        </button>
        <button className="btn btn-reject btn-sm"  disabled={busy} onClick={() => act(() => onReject(item.filename))}>
          ✗ Reject
        </button>
      </div>
    </div>
  );
}

export default function Approvals() {
  const [items,   setItems]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [toast,   setToast]   = useState('');
  const [isDrag,  setIsDrag]  = useState(false);
  const dropRef = useRef(null);

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(''), 3000);
  };

  const fetchPending = useCallback(async () => {
    try {
      const data = await apiFetch('/api/pending');
      setItems(data);
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchPending(); }, [fetchPending]);

  async function approve(filename) {
    try {
      await apiFetch(`/api/pending/${encodeURIComponent(filename)}/approve`, { method: 'POST' });
      setItems(i => i.filter(x => x.filename !== filename));
      showToast(`Approved: ${filename}`);
    } catch (e) { showToast(e.message, 'error'); }
  }

  async function reject(filename) {
    try {
      await apiFetch(`/api/pending/${encodeURIComponent(filename)}/reject`, { method: 'POST' });
      setItems(i => i.filter(x => x.filename !== filename));
      showToast(`Rejected: ${filename}`);
    } catch (e) { showToast(e.message, 'error'); }
  }

  // Drag-and-drop: drop a file onto the zone to place it in Pending_Approval (simulated)
  function onDrop(e) {
    e.preventDefault(); setIsDrag(false);
    showToast('Drag-drop: use Task Creator to add files to /Needs_Action.', 'error');
  }

  if (loading) return <p className="loading"><span className="spinner" /> Loading approvals…</p>;

  return (
    <>
      {toast && (
        <div className="toast-container">
          <div className={`toast ${toast.type}`}>{toast.msg}</div>
        </div>
      )}

      <div className="stats">
        <div className="stat">
          <div className="stat-num">{items.length}</div>
          <div className="stat-lbl">Pending</div>
        </div>
      </div>

      <div className="card">
        <div className="card-title">📋 Approval Queue</div>

        {items.length === 0 ? (
          <div
            ref={dropRef}
            className={`drop-zone ${isDrag ? 'drag-over' : ''}`}
            onDragOver={e => { e.preventDefault(); setIsDrag(true); }}
            onDragLeave={() => setIsDrag(false)}
            onDrop={onDrop}
          >
            <div style={{ fontSize: 32 }}>✅</div>
            <p>All clear — no items pending approval.</p>
            <p style={{ fontSize: 11, marginTop: 6 }}>Drag files here or use Task Creator</p>
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 10, marginBottom: 14 }}>
              <button className="btn btn-approve btn-sm" onClick={() => items.forEach(i => approve(i.filename))}>
                ✓ Approve All
              </button>
              <button className="btn btn-reject btn-sm"  onClick={() => items.forEach(i => reject(i.filename))}>
                ✗ Reject All
              </button>
              <button className="btn btn-sm" style={{ background: 'var(--border)', color: 'var(--text)' }}
                      onClick={fetchPending}>↻ Refresh</button>
            </div>
            {items.map(item => (
              <PendingCard key={item.filename} item={item} onApprove={approve} onReject={reject} />
            ))}
          </>
        )}
      </div>
    </>
  );
}
