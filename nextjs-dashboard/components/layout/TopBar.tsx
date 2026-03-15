'use client';
import { useState, useEffect } from 'react';
import { Shield, RefreshCw, Bell, ChevronRight, Zap } from 'lucide-react';
import { format } from 'date-fns';

export default function TopBar({ onRefresh }: { onRefresh?: () => void }) {
  const [now, setNow] = useState(new Date());
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  async function handleRefresh() {
    setRefreshing(true);
    onRefresh?.();
    setTimeout(() => setRefreshing(false), 1000);
  }

  return (
    <header
      className="flex items-center gap-3 px-6 py-3 sticky top-0 z-40"
      style={{ background: 'rgba(13,14,26,0.95)', borderBottom: '1px solid #1e2035', backdropFilter: 'blur(12px)' }}
    >
      {/* DRY RUN badge */}
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg flex-1"
           style={{ background: 'rgba(20,184,166,0.12)', border: '1px solid rgba(20,184,166,0.25)' }}>
        <Shield size={13} className="text-teal-400 flex-shrink-0" />
        <span className="text-xs font-bold text-teal-400 mr-1">DRY RUN</span>
        <span className="text-xs hidden sm:inline" style={{ color: '#64748b' }}>
          Safe mode active. No emails, posts, or payments will execute.
        </span>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-3 flex-shrink-0">
        {/* Timestamp */}
        <span className="text-xs font-mono hidden md:block" style={{ color: '#64748b' }}>
          {format(now, 'MMM dd, yyyy HH:mm:ss')}
        </span>

        {/* Refresh */}
        <button
          onClick={handleRefresh}
          className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors hover:bg-[#1a1b2e]"
          style={{ border: '1px solid #1e2035' }}
        >
          <RefreshCw size={14} className={`text-[#64748b] ${refreshing ? 'animate-spin' : ''}`} />
        </button>

        {/* Notifications */}
        <button className="relative w-8 h-8 rounded-lg flex items-center justify-center transition-colors hover:bg-[#1a1b2e]"
                style={{ border: '1px solid #1e2035' }}>
          <Bell size={14} className="text-[#64748b]" />
          <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-red-500" />
        </button>

        {/* User avatar */}
        <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white cursor-pointer"
             style={{ background: 'linear-gradient(135deg, #7c3aed, #3b82f6)' }}>
          D
        </div>

        {/* Go LIVE button */}
        <button className="flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-bold text-white transition-all hover:opacity-90 btn-transition"
                style={{ background: 'linear-gradient(135deg, #7c3aed, #4f46e5)' }}>
          <Zap size={12} />
          Go LIVE
          <ChevronRight size={12} />
        </button>
      </div>
    </header>
  );
}
