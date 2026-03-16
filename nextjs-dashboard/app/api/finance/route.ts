import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({
    month: 'March 2026',
    income: 8500,
    expenses: 3200,
    net: 5300,
    currency: 'PKR',
    incomeChangePercent: 34,
    incomeBreakdown: [
      { label: 'Client Retainers', amount: 5000 },
      { label: 'Project Work',     amount: 2500 },
      { label: 'Consulting',       amount: 1000 },
    ],
    expensesBreakdown: [
      { label: 'SaaS Tools',   amount: 800 },
      { label: 'API Credits',  amount: 600 },
      { label: 'Contractors',  amount: 1800 },
    ],
  });
}
