'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Zap, LayoutDashboard, CheckSquare, Activity, Bot,
  Mail, Share2, MessageCircle, Webhook,
  DollarSign, Building2, FileText, Search,
  LogOut, ChevronRight
} from 'lucide-react';
import clsx from 'clsx';

const navSections = [
  {
    label: 'MAIN',
    items: [
      { label: 'Dashboard',    href: '/',         icon: LayoutDashboard, badge: null },
      { label: 'Approvals',    href: '/approvals',icon: CheckSquare,     badge: '3' },
      { label: 'Activity Logs',href: '/activity', icon: Activity,        badge: null },
      { label: 'AI Bots',      href: '/bots',     icon: Bot,             badge: null },
    ],
  },
  {
    label: 'SEND & POST',
    items: [
      { label: 'Send Email',   href: '/email',    icon: Mail,            badge: null },
      { label: 'Social Media', href: '/social',   icon: Share2,          badge: null },
      { label: 'WhatsApp',     href: '/whatsapp', icon: MessageCircle,   badge: null },
      { label: 'Webhooks',     href: '/webhooks', icon: Webhook,         badge: null },
    ],
  },
  {
    label: 'FINANCE & REPORTS',
    items: [
      { label: 'Finance',      href: '/finance',  icon: DollarSign,      badge: null },
      { label: 'Bank Monitor', href: '/bank',     icon: Building2,       badge: null },
      { label: 'CEO Report',   href: '/report',   icon: FileText,        badge: null },
      { label: 'AI Search',    href: '/search',   icon: Search,          badge: null },
    ],
  },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside
      className="fixed left-0 top-0 h-screen flex flex-col z-50"
      style={{ width: 240, background: '#0a0b14', borderRight: '1px solid #1e2035' }}
    >
      {/* Logo */}
      <div className="px-4 py-5 flex items-start justify-between" style={{ borderBottom: '1px solid #1e2035' }}>
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center"
               style={{ background: 'linear-gradient(135deg, #7c3aed, #3b82f6)' }}>
            <Zap size={18} className="text-white" />
          </div>
          <div>
            <div className="font-bold text-sm leading-tight" style={{ color: '#f1f5f9' }}>AI Employee</div>
            <div className="text-xs leading-tight" style={{ color: '#64748b' }}>Operations Hub</div>
          </div>
        </div>
        <span className="text-xs font-bold px-2 py-0.5 rounded-full mt-1"
              style={{ background: 'rgba(124,58,237,0.2)', color: '#a78bfa', border: '1px solid rgba(124,58,237,0.3)' }}>
          ADMIN
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-5">
        {navSections.map((section) => (
          <div key={section.label}>
            <p className="px-3 mb-1.5 text-xs font-semibold tracking-widest" style={{ color: '#374151' }}>
              {section.label}
            </p>
            <ul className="space-y-0.5">
              {section.items.map((item) => {
                const active = pathname === item.href;
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={clsx(
                        'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all duration-150 group relative',
                        active
                          ? 'bg-[#1a1b2e] text-[#f1f5f9]'
                          : 'text-[#64748b] hover:bg-[#13141f] hover:text-[#94a3b8]'
                      )}
                      style={active ? { borderLeft: '3px solid #3b82f6', paddingLeft: '9px' } : {}}
                    >
                      {/* Active indicator dot */}
                      {active && (
                        <span className="absolute right-3 w-1.5 h-1.5 rounded-full bg-blue-500 dot-pulse" />
                      )}
                      <Icon size={16} className={active ? 'text-blue-400' : 'text-current'} />
                      <span className="flex-1 font-medium">{item.label}</span>
                      {item.badge && (
                        <span className="text-xs font-bold px-1.5 py-0.5 rounded-full"
                              style={{ background: 'rgba(245,158,11,0.2)', color: '#f59e0b' }}>
                          {item.badge}
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* User footer */}
      <div className="px-3 py-3" style={{ borderTop: '1px solid #1e2035' }}>
        <div className="flex items-center gap-3 p-2 rounded-lg hover:bg-[#13141f] transition-colors cursor-pointer group">
          <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-sm font-bold text-white"
               style={{ background: 'linear-gradient(135deg, #7c3aed, #3b82f6)' }}>
            D
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold truncate" style={{ color: '#f1f5f9' }}>demo</div>
            <div className="text-xs truncate" style={{ color: '#64748b' }}>Administrator</div>
          </div>
          <LogOut size={15} className="text-[#374151] group-hover:text-red-400 transition-colors flex-shrink-0" />
        </div>
      </div>
    </aside>
  );
}
