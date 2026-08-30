"use client";

import { Bell, Moon, PlugZap, RefreshCw, Sun } from "lucide-react";

import type { Theme } from "@/hooks/use-theme";
import type { ApplicationContext, DataMode } from "@/lib/types";

type TopbarProps = {
  title: string;
  mode: DataMode;
  project: string;
  applications: ApplicationContext[];
  selectedApplication: string;
  timeRange: string;
  systemHealthy: boolean;
  incidentCount: number;
  loading: boolean;
  theme: Theme;
  onApplicationChange: (value: string) => void;
  onTimeRangeChange: (value: string) => void;
  onThemeToggle: () => void;
  onConnect: () => void;
  onRefresh: () => void;
  onNotifications: () => void;
  onProfile: () => void;
};

export function Topbar(props: TopbarProps) {
  return <header className="topbar">
    <div className="topbar-heading"><h1>{props.title}</h1><span>{props.mode === "live" ? "Live workspace" : "API disconnected"}</span></div>
    <div className="topbar-context">
      <label className="context-control"><span>Project</span><strong>{props.project}</strong></label>
      <label className="context-control"><span>Application</span><select value={props.selectedApplication} onChange={(event) => props.onApplicationChange(event.target.value)}><option value="all">All applications</option>{props.applications.map((application) => <option key={application.id} value={application.id}>{application.name}</option>)}</select></label>
      <label className="context-control"><span>Range</span><select value={props.timeRange} onChange={(event) => props.onTimeRangeChange(event.target.value)}><option value="24h">24 hours</option><option value="7d">7 days</option><option value="30d">30 days</option></select></label>
      <div className="health-control"><span>Health</span><strong><i data-healthy={props.systemHealthy} />{props.systemHealthy ? "Healthy" : "Degraded"}</strong></div>
    </div>
    <div className="topbar-actions">
      {props.mode === "live" && <button className="icon-button" disabled={props.loading} onClick={props.onRefresh} title="Refresh data" type="button"><RefreshCw className={props.loading ? "spin" : undefined} size={18} /></button>}
      <button aria-label={props.theme === "light" ? "Enable night mode" : "Enable light mode"} className="icon-button" onClick={props.onThemeToggle} title={props.theme === "light" ? "Enable night mode" : "Enable light mode"} type="button">{props.theme === "light" ? <Moon size={18} /> : <Sun size={18} />}</button>
      <button className="connect-button" onClick={props.onConnect} type="button"><PlugZap size={16} />{props.mode === "live" ? "API" : "Connect"}</button>
      <button className="icon-button" onClick={props.onNotifications} title="Open incidents" type="button"><Bell size={18} />{props.incidentCount > 0 && <b>{Math.min(99, props.incidentCount)}</b>}</button>
      <button className="top-avatar" onClick={props.onProfile} title="Open access profile" type="button">API</button>
    </div>
  </header>;
}
