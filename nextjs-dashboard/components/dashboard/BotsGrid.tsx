'use client';
import { useState } from 'react';
import { Play, Square } from 'lucide-react';
import type { BotStatus } from '@/lib/types';

export default function BotsGrid({
  bots,
  onToggle,
}: {
  bots: BotStatus[];
  onToggle: (name: string) => void;
}) {
  return (
    <div className="animate-fade-in">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold text-sm" style={{ color: '#f1f5f9' }}>
          AI Bots &amp; Workers
        </h2>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-green-500" />
          <span className="text-xs" style={{ color: '#64748b' }}>
            {bots.filter(b => b.status === 'running').length} running
          </span>
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {bots.map((bot) => (
          <BotCard key={bot.name} bot={bot} onToggle={onToggle} />
        ))}
      </div>
    </div>
  );
}

function BotCard({ bot, onToggle }: { bot: BotStatus; onToggle: (name: string) => void }) {
  const [pending, setPending] = useState(false);

  const isRunning = bot.status === 'running';
  const dotColor  = isRunning ? '#10b981' : '#374151';

  async function handleToggle() {
    setPending(true);
    onToggle(bot.name);
    setTimeout(() => setPending(false), 800);
  }

  return (
    <div
      className="rounded-xl p-4 card-hover group cursor-default"
      style={{ background: '#13141f', border: `1px solid ${isRunning ? '#1e2035' : '#1a1a2a'}` }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-xl" role="img" aria-label={bot.displayName}>{bot.emoji}</span>
        {/* Status dot */}
        <div className="flex items-center gap-1.5">
          <span
            className={`w-2 h-2 rounded-full ${isRunning ? 'dot-pulse' : ''}`}
            style={{ background: dotColor, boxShadow: isRunning ? `0 0 6px ${dotColor}88` : 'none' }}
          />
        </div>
      </div>

      {/* Name */}
      <p className="text-sm font-semibold mb-0.5 leading-tight" style={{ color: isRunning ? '#f1f5f9' : '#64748b' }}>
        {bot.displayName}
      </p>
      <p className="text-xs mb-3" style={{ color: '#374151' }}>
        {bot.description}
      </p>

      {/* Status line */}
      <div className="flex items-center justify-between">
        <div>
          <span className={`text-xs font-semibold ${isRunning ? 'text-green-400' : 'text-[#374151]'}`}>
            {isRunning ? 'Running' : 'Stopped'}
          </span>
          {bot.uptime && isRunning && (
            <span className="text-xs ml-1" style={{ color: '#374151' }}>• {bot.uptime}</span>
          )}
        </div>

        {/* Toggle button (visible on hover) */}
        <button
          onClick={handleToggle}
          disabled={pending}
          className="opacity-0 group-hover:opacity-100 transition-opacity w-6 h-6 rounded-md flex items-center justify-center"
          style={{ background: isRunning ? 'rgba(239,68,68,0.15)' : 'rgba(16,185,129,0.15)' }}
          title={isRunning ? 'Stop bot' : 'Start bot'}
        >
          {isRunning
            ? <Square size={10} className="text-red-400" />
            : <Play    size={10} className="text-green-400" />
          }
        </button>
      </div>

      {/* Last action */}
      {bot.lastAction && (
        <p className="text-xs mt-2 truncate" style={{ color: '#374151' }} title={bot.lastAction}>
          {bot.lastAction}
        </p>
      )}
    </div>
  );
}
