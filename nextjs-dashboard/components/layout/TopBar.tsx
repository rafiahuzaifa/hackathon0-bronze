'use client';
import { useState, useEffect } from 'react';
import { Shield, RefreshCw, Bell, Zap, Settings, CheckCircle, AlertCircle, X } from 'lucide-react';
import { format } from 'date-fns';
import Link from 'next/link';

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function TopBar({ onRefresh }: { onRefresh?: () => void }) {
  const [now, setNow] = useState(new Date());
  const [refreshing, setRefreshing] = useState(false);
  const [isLive, setIsLive] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [toast, setToast] = useState<{ msg: string; type: 'ok' | 'err' } | null>(null);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    // Check current mode from backend
    fetch(`${BASE}/health`)
      .then(r => r.json())
      .then(d => setIsLive(!d.dry_run))
      .catch(() => {});
    return () => clearInterval(t);
  }, []);

  function showToast(msg: string, type: 'ok' | 'err') {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  }

  async function handleRefresh() {
    setRefreshing(true);
    onRefresh?.();
    setTimeout(() => setRefreshing(false), 1000);
  }

  async function toggleMode() {
    if (!isLive) {
      // Going live — show confirmation first
      setShowConfirm(true);
      return;
    }
    // Going back to demo — no confirmation needed
    await doToggle(false);
  }

  async function doToggle(goLive: boolean) {
    setShowConfirm(false);
    setToggling(true);
    try {
      const res = await fetch(`${BASE}/api/system/mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ live: goLive }),
      });
      if (res.ok) {
        setIsLive(goLive);
        showToast(
          goLive ? '🔴 LIVE MODE — real actions enabled' : '🛡️ Demo mode — safe mode active',
          'ok'
        );
      } else {
        showToast('Backend not reachable. Run the API server first.', 'err');
      }
    } catch {
      showToast('Cannot reach backend. Start: cd ai_employee && python -m uvicorn api.server:app', 'err');
    } finally {
      setToggling(false);
    }
  }

  return (
    <>
      <header
        className="flex items-center gap-3 px-6 py-3 sticky top-0 z-40"
        style={{ background: 'rgba(13,14,26,0.95)', borderBottom: '1px solid #1e2035', backdropFilter: 'blur(12px)' }}
      >
        {/* Mode badge */}
        <div
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg flex-1 transition-all duration-300"
          style={isLive
            ? { background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.35)' }
            : { background: 'rgba(20,184,166,0.12)', border: '1px solid rgba(20,184,166,0.25)' }}
        >
          {isLive
            ? <><span className="w-2 h-2 rounded-full bg-red-500 animate-pulse flex-shrink-0" />
                <span className="text-xs font-bold text-red-400 mr-1">LIVE</span>
                <span className="text-xs hidden sm:inline" style={{ color: '#94a3b8' }}>
                  Real actions active — emails, posts, messages will execute
                </span></>
            : <><Shield size={13} className="text-teal-400 flex-shrink-0" />
                <span className="text-xs font-bold text-teal-400 mr-1">DEMO</span>
                <span className="text-xs hidden sm:inline" style={{ color: '#64748b' }}>
                  Safe mode — no real emails, posts or payments will execute
                </span></>
          }
        </div>

        {/* Right side */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-xs font-mono hidden md:block" style={{ color: '#64748b' }}>
            {format(now, 'MMM dd HH:mm:ss')}
          </span>

          <button onClick={handleRefresh}
            className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors hover:bg-[#1a1b2e]"
            style={{ border: '1px solid #1e2035' }}>
            <RefreshCw size={14} className={`text-[#64748b] ${refreshing ? 'animate-spin' : ''}`} />
          </button>

          <button className="relative w-8 h-8 rounded-lg flex items-center justify-center hover:bg-[#1a1b2e]"
            style={{ border: '1px solid #1e2035' }}>
            <Bell size={14} className="text-[#64748b]" />
            <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-red-500" />
          </button>

          {/* Setup link */}
          <Link href="/setup"
            className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-[#1a1b2e] transition-colors"
            style={{ border: '1px solid #1e2035' }} title="Setup credentials">
            <Settings size={14} className="text-[#64748b]" />
          </Link>

          {/* Go Live / Demo toggle */}
          <button
            onClick={toggleMode}
            disabled={toggling}
            className="flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-bold text-white transition-all disabled:opacity-50"
            style={isLive
              ? { background: 'rgba(239,68,68,0.2)', border: '1px solid rgba(239,68,68,0.5)', color: '#f87171' }
              : { background: 'linear-gradient(135deg,#7c3aed,#4f46e5)' }}
          >
            {toggling
              ? <RefreshCw size={12} className="animate-spin" />
              : <Zap size={12} />}
            {isLive ? 'Go DEMO' : 'Go LIVE'}
          </button>
        </div>
      </header>

      {/* Go Live confirmation modal */}
      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}>
          <div className="rounded-2xl p-6 max-w-md w-full space-y-4"
            style={{ background: '#0f1020', border: '1px solid rgba(239,68,68,0.3)' }}>
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-red-400">⚠️ Enable LIVE Mode?</h2>
              <button onClick={() => setShowConfirm(false)}><X size={16} className="text-[#475569]" /></button>
            </div>
            <div className="space-y-2 text-sm" style={{ color: '#94a3b8' }}>
              <p>In LIVE mode, the AI Employee will:</p>
              <ul className="space-y-1 ml-3">
                {['Send real emails from your Gmail account',
                  'Post on LinkedIn, Twitter, Facebook, Instagram',
                  'Send WhatsApp messages to real contacts',
                  'Process real bank transactions',
                  'All actions require credentials in /setup'].map(item => (
                  <li key={item} className="flex items-start gap-2">
                    <span className="text-red-400 mt-0.5">•</span>{item}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs" style={{ color: '#64748b' }}>
                Make sure you have set up your credentials in <strong style={{ color: '#a78bfa' }}>/setup</strong> first.
              </p>
            </div>
            <div className="flex gap-3 pt-2">
              <button onClick={() => doToggle(true)}
                className="flex-1 py-2 rounded-lg text-sm font-bold text-white"
                style={{ background: 'linear-gradient(135deg,#ef4444,#dc2626)' }}>
                Yes, Go LIVE
              </button>
              <button onClick={() => setShowConfirm(false)}
                className="flex-1 py-2 rounded-lg text-sm font-semibold"
                style={{ background: '#1e2035', color: '#94a3b8', border: '1px solid #2a2d45' }}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-5 right-5 z-50 flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium shadow-xl"
          style={toast.type === 'ok'
            ? { background: '#0f1020', border: '1px solid #34d399', color: '#34d399' }
            : { background: '#0f1020', border: '1px solid #f87171', color: '#f87171' }}>
          {toast.type === 'ok' ? <CheckCircle size={15} /> : <AlertCircle size={15} />}
          {toast.msg}
        </div>
      )}
    </>
  );
}
