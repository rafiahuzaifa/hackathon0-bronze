'use client';
import { mockData } from '@/lib/api';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';

export default function FinancePage() {
  const fin = mockData.finance();
  const chartData = [
    { name: 'Income',   value: fin.income,   color: '#10b981' },
    { name: 'Expenses', value: fin.expenses,  color: '#ef4444' },
    { name: 'Net',      value: fin.net,       color: '#3b82f6' },
  ];

  return (
    <div className="max-w-3xl animate-fade-in space-y-6">
      <h1 className="text-xl font-bold" style={{ color: '#f1f5f9' }}>Finance — {fin.month}</h1>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Income',   value: fin.income,   color: '#10b981' },
          { label: 'Expenses', value: fin.expenses,  color: '#ef4444' },
          { label: 'Net',      value: fin.net,       color: '#3b82f6' },
        ].map(c => (
          <div key={c.label} className="rounded-xl p-4" style={{ background: '#13141f', border: '1px solid #1e2035' }}>
            <p className="text-xs font-semibold tracking-widest mb-2" style={{ color: '#374151' }}>{c.label.toUpperCase()}</p>
            <p className="text-2xl font-bold" style={{ color: c.color }}>{fin.currency} {c.value.toLocaleString()}</p>
          </div>
        ))}
      </div>

      {/* Bar chart */}
      <div className="rounded-xl p-5" style={{ background: '#13141f', border: '1px solid #1e2035' }}>
        <h2 className="text-sm font-semibold mb-4" style={{ color: '#f1f5f9' }}>Monthly Overview</h2>
        <ResponsiveContainer width="100%" height={180}>
          <BarChart data={chartData} barSize={40}>
            <XAxis dataKey="name" tick={{ fill: '#64748b', fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={{ background: '#1a1b2e', border: '1px solid #1e2035', borderRadius: 8, color: '#f1f5f9' }}
              formatter={(v: number) => [`${fin.currency} ${v.toLocaleString()}`, '']}
            />
            <Bar dataKey="value" radius={[6, 6, 0, 0]}>
              {chartData.map((c, i) => <Cell key={i} fill={c.color} fillOpacity={0.85} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Breakdowns */}
      <div className="grid grid-cols-2 gap-4">
        <BreakdownCard title="Income Sources" items={fin.incomeBreakdown} currency={fin.currency} color="#10b981" />
        <BreakdownCard title="Expense Breakdown" items={fin.expensesBreakdown} currency={fin.currency} color="#ef4444" />
      </div>
    </div>
  );
}

function BreakdownCard({ title, items, currency, color }: {
  title: string; items: { label: string; amount: number }[]; currency: string; color: string;
}) {
  const total = items.reduce((s, i) => s + i.amount, 0);
  return (
    <div className="rounded-xl p-4" style={{ background: '#13141f', border: '1px solid #1e2035' }}>
      <h3 className="text-xs font-semibold tracking-widest mb-3" style={{ color: '#374151' }}>{title.toUpperCase()}</h3>
      {items.map(item => (
        <div key={item.label} className="flex items-center justify-between py-2 border-b last:border-0" style={{ borderColor: '#1e2035' }}>
          <span className="text-xs" style={{ color: '#94a3b8' }}>{item.label}</span>
          <div className="text-right">
            <span className="text-xs font-semibold" style={{ color }}>{currency} {item.amount.toLocaleString()}</span>
            <span className="text-xs ml-1" style={{ color: '#374151' }}>{Math.round((item.amount / total) * 100)}%</span>
          </div>
        </div>
      ))}
    </div>
  );
}
