'use client';
import { useState } from 'react';
import { mockData, api } from '@/lib/api';
import BotsGrid from '@/components/dashboard/BotsGrid';
import type { BotStatus } from '@/lib/types';

export default function BotsPage() {
  const [bots, setBots] = useState<BotStatus[]>(mockData.bots());

  async function handleToggle(name: string) {
    const result = await api.toggleBot(name).catch(() => null);
    setBots(prev => prev.map(b =>
      b.name === name
        ? { ...b, status: result ? result.status as BotStatus['status'] : (b.status === 'running' ? 'stopped' : 'running') }
        : b
    ));
  }

  return (
    <div className="animate-fade-in">
      <h1 className="text-xl font-bold mb-6" style={{ color: '#f1f5f9' }}>AI Bots &amp; Workers</h1>
      <BotsGrid bots={bots} onToggle={handleToggle} />
    </div>
  );
}
