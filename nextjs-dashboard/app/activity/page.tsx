'use client';
import { useState } from 'react';
import { mockData } from '@/lib/api';
import ActivityPanel from '@/components/dashboard/ActivityPanel';

export default function ActivityPage() {
  const events = mockData.activity();
  return (
    <div className="max-w-3xl animate-fade-in">
      <h1 className="text-xl font-bold mb-6" style={{ color: '#f1f5f9' }}>Activity Logs</h1>
      <ActivityPanel events={events} />
    </div>
  );
}
