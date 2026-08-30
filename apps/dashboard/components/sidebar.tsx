"use client";

import { Activity, Boxes, CircleGauge, LayoutDashboard, Settings, ShieldAlert, UserRound } from "lucide-react";

import type { NavigationItem, ViewId } from "@/lib/types";

const navigation: NavigationItem[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "runs", label: "Runs", icon: Activity },
  { id: "budgets", label: "Budgets", icon: CircleGauge },
  { id: "incidents", label: "Incidents", icon: ShieldAlert },
  { id: "models", label: "Models", icon: Boxes },
  { id: "settings", label: "Settings", icon: Settings },
];

type SidebarProps = {
  activeView: ViewId;
  systemStatus: string;
  systemHealthy: boolean;
  organization: string;
  onNavigate: (view: ViewId) => void;
};

export function Sidebar({ activeView, systemStatus, systemHealthy, organization, onNavigate }: SidebarProps) {
  return <aside className="sidebar">
    <button className="brand" onClick={() => onNavigate("overview")} type="button" aria-label="Open overview">
      <span className="brand-mark">c0</span><span className="brand-word">c0ntr0l</span>
    </button>
    <div className="organization-label"><span>Workspace</span><strong>{organization}</strong></div>
    <nav className="primary-nav" aria-label="Primary navigation">
      {navigation.map((item) => {
        const Icon = item.icon;
        return <button aria-label={item.label} className="nav-item" data-active={activeView === item.id} key={item.id} onClick={() => onNavigate(item.id)} type="button">
          <Icon aria-hidden="true" size={18} strokeWidth={1.8} /><span>{item.label}</span>
        </button>;
      })}
    </nav>
    <div className="sidebar-lower">
      <div className="system-state"><span className="system-dot" data-healthy={systemHealthy} /><div><strong>System</strong><span>{systemStatus}</span></div></div>
      <button aria-label="Profile" className="profile-nav" data-active={activeView === "profile"} onClick={() => onNavigate("profile")} type="button">
        <span className="avatar">API</span><span><strong>Project access</strong><small>Scoped session</small></span><UserRound size={16} />
      </button>
    </div>
  </aside>;
}
