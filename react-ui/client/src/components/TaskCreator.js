import React, { useState, useRef } from 'react';
import { apiFetch } from '../App';

export default function TaskCreator() {
  const [title,    setTitle]    = useState('');
  const [content,  setContent]  = useState('');
  const [category, setCategory] = useState('manual');
  const [loading,  setLoading]  = useState(false);
  const [result,   setResult]   = useState(null);
  const [isDrag,   setIsDrag]   = useState(false);
  const dropRef = useRef(null);

  async function submit(e) {
    e.preventDefault();
    if (!content.trim()) return;
    setLoading(true); setResult(null);
    try {
      const r = await apiFetch('/api/task', {
        method: 'POST', body: { title: title || 'Task', content, category },
      });
      setResult({ ok: true, msg: `Created: ${r.filename}` });
      setTitle(''); setContent('');
    } catch (err) {
      setResult({ ok: false, msg: err.message });
    } finally {
      setLoading(false);
    }
  }

  // Drop a .txt or .md file — read its text into the content field
  function onDrop(e) {
    e.preventDefault(); setIsDrag(false);
    const file = e.dataTransfer.files[0];
    if (!file) return;
    setTitle(file.name.replace(/\.\w+$/, ''));
    const reader = new FileReader();
    reader.onload = ev => setContent(ev.target.result);
    reader.readAsText(file);
  }

  return (
    <div className="card" style={{ maxWidth: 620 }}>
      <div className="card-title">📝 Task Creator — Drop into /Needs_Action</div>

      {/* Drop zone */}
      <div
        ref={dropRef}
        className={`drop-zone ${isDrag ? 'drag-over' : ''}`}
        style={{ marginBottom: 20 }}
        onDragOver={e => { e.preventDefault(); setIsDrag(true); }}
        onDragLeave={() => setIsDrag(false)}
        onDrop={onDrop}
      >
        <div style={{ fontSize: 28 }}>📂</div>
        <p>Drop a .md or .txt file here to pre-fill</p>
      </div>

      <form onSubmit={submit}>
        <div className="form-group">
          <label>Title</label>
          <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Task title…" />
        </div>
        <div className="form-group">
          <label>Category</label>
          <select value={category} onChange={e => setCategory(e.target.value)}>
            <option value="manual">Manual</option>
            <option value="email">Email</option>
            <option value="payment">Payment</option>
            <option value="social">Social Media</option>
            <option value="linkedin">LinkedIn</option>
            <option value="research">Research</option>
          </select>
        </div>
        <div className="form-group">
          <label>Content *</label>
          <textarea
            value={content} onChange={e => setContent(e.target.value)}
            placeholder="Task description or instructions…" rows={6} required
          />
        </div>
        <button type="submit" className="btn btn-primary" disabled={loading || !content.trim()}>
          {loading ? <><span className="spinner" /> Creating…</> : '+ Add to Needs_Action'}
        </button>
        {result && (
          <div style={{ marginTop: 12, color: result.ok ? 'var(--green)' : 'var(--red)', fontSize: 13 }}>
            {result.ok ? '✓ ' : '✗ '}{result.msg}
          </div>
        )}
      </form>
    </div>
  );
}
