import type { Metadata } from 'next';
import './globals.css';
import Sidebar from '@/components/layout/Sidebar';
import TopBar  from '@/components/layout/TopBar';

export const metadata: Metadata = {
  title: 'AI Employee — Operations Hub',
  description: 'Personal AI Employee System — Gold Tier Panaversity Hackathon 2026',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body style={{ background: '#0d0e1a', color: '#f1f5f9' }}>
        <div className="flex min-h-screen">
          {/* Sidebar */}
          <Sidebar />

          {/* Main content */}
          <div className="flex-1 flex flex-col" style={{ marginLeft: 240 }}>
            <TopBar />
            <main className="flex-1 p-6 overflow-auto">
              {children}
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
