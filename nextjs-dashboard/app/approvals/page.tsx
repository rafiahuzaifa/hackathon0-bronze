'use client';
import { useState } from 'react';
import { mockData, api } from '@/lib/api';
import ApprovalsPanel from '@/components/dashboard/ApprovalsPanel';

export default function ApprovalsPage() {
  const [items, setItems] = useState(mockData.approvals());

  async function handleApprove(id: string) {
    await api.approveItem(id).catch(() => {});
    setItems(prev => prev.filter(a => a.id !== id));
  }
  async function handleReject(id: string) {
    await api.rejectItem(id).catch(() => {});
    setItems(prev => prev.filter(a => a.id !== id));
  }

  return (
    <div className="max-w-2xl animate-fade-in">
      <h1 className="text-xl font-bold mb-6" style={{ color: '#f1f5f9' }}>Approval Queue</h1>
      <ApprovalsPanel items={items} onApprove={handleApprove} onReject={handleReject} />
    </div>
  );
}
