"use client";

import { useMemo, useState } from "react";
import { PlugZap } from "lucide-react";

import { BudgetsView } from "@/components/budgets-view";
import { ConnectionDialog } from "@/components/connection-dialog";
import { IncidentsView } from "@/components/incidents-view";
import { ModelsView } from "@/components/models-view";
import { Overview } from "@/components/overview";
import { ProfileView } from "@/components/profile-view";
import { RunsView } from "@/components/runs-view";
import { SettingsView } from "@/components/settings-view";
import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";
import { useConsoleSettings } from "@/hooks/use-console-settings";
import { useControlData } from "@/hooks/use-control-data";
import { useModelPolicies } from "@/hooks/use-model-policies";
import { useTheme } from "@/hooks/use-theme";
import type { Execution, ViewId } from "@/lib/types";

const titles: Record<ViewId, string> = {
  overview: "Overview", runs: "Executions", budgets: "Budgets", incidents: "Incidents",
  models: "Models", settings: "Settings", profile: "Profile",
};
const ranges: Record<string, number> = { "24h": 24 * 60 * 60 * 1000, "7d": 7 * 24 * 60 * 60 * 1000, "30d": 30 * 24 * 60 * 60 * 1000 };

export function AppShell() {
  const [activeView, setActiveView] = useState<ViewId>("overview");
  const [connectionOpen, setConnectionOpen] = useState(false);
  const [application, setApplication] = useState("all");
  const [timeRange, setTimeRange] = useState("24h");
  const [requestedExecution, setRequestedExecution] = useState<Execution | null>(null);
  const data = useControlData();
  const consoleState = useConsoleSettings();
  const modelState = useModelPolicies();
  const themeState = useTheme();
  const systemHealthy = data.mode === "live" && (data.health?.status === "ok" || data.health?.status === "healthy");
  const systemStatus = data.mode === "disconnected" ? "Disconnected" : systemHealthy ? "Operational" : "Degraded";
  const executions = useMemo(() => {
    const cutoff = Date.now() - ranges[timeRange];
    return data.executions.filter((run) => (application === "all" || run.applicationId === application) && new Date(run.startedAt).getTime() >= cutoff);
  }, [application, data.executions, timeRange]);
  const incidents = useMemo(() => data.incidents.filter((incident) => executions.some((run) => run.id === incident.executionId)), [data.incidents, executions]);
  const notificationCount = incidents.filter((incident) => incident.status === "open" && ((incident.severity === "critical" && consoleState.settings.notifyCritical) || (incident.severity !== "critical" && consoleState.settings.notifyWarnings))).length;

  function openRun(run: Execution) {
    setRequestedExecution(run);
    setActiveView("runs");
  }

  function renderView() {
    if (activeView === "overview") return <Overview executions={executions} incidents={incidents} modelPolicies={modelState.policies} onOpenRun={openRun} onViewIncidents={() => setActiveView("incidents")} onViewModels={() => setActiveView("models")} onViewRuns={() => setActiveView("runs")} settings={consoleState.settings} workspace={data.workspace} />;
    if (activeView === "runs") return <RunsView cancelExecution={data.cancelExecution} executions={executions} loadExecution={data.loadExecution} loadIntervention={data.loadIntervention} onSelectionHandled={() => setRequestedExecution(null)} recoverExecution={data.recoverExecution} requestedExecution={requestedExecution} settings={consoleState.settings} />;
    if (activeView === "budgets") return <BudgetsView executions={executions} modelPolicies={modelState.policies} workspace={data.workspace} />;
    if (activeView === "incidents") return <IncidentsView executions={executions} incidents={incidents} onOpenRun={openRun} onStatus={data.updateIncidentStatus} />;
    if (activeView === "models") return <ModelsView connection={data.connection} executions={executions} onLimit={modelState.updateLimit} onMode={modelState.updateMode} policies={modelState.policies} />;
    if (activeView === "settings") return <SettingsView connection={data.connection} health={data.health} mode={data.mode} onConnection={() => setConnectionOpen(true)} onUpdate={consoleState.update} settings={consoleState.settings} />;
    return <ProfileView connection={data.connection} mode={data.mode} onDisconnect={data.disconnect} workspace={data.workspace} />;
  }

  return <div className="app-shell">
    <Sidebar activeView={activeView} onNavigate={setActiveView} organization={data.workspace.organizationName} systemHealthy={systemHealthy} systemStatus={systemStatus} />
    <div className="workspace"><Topbar applications={data.workspace.applications} incidentCount={notificationCount} loading={data.loading} mode={data.mode} onApplicationChange={setApplication} onConnect={() => setConnectionOpen(true)} onNotifications={() => setActiveView("incidents")} onProfile={() => setActiveView("profile")} onRefresh={() => void data.refresh()} onThemeToggle={themeState.toggleTheme} onTimeRangeChange={setTimeRange} project={data.workspace.projectName} selectedApplication={application} systemHealthy={systemHealthy} theme={themeState.theme} timeRange={timeRange} title={titles[activeView]} />
      {data.error && data.mode === "live" && <div className="runtime-banner">Refresh failed: {data.error}</div>}
      <main className="main-content">{data.mode === "disconnected" ? <section className="panel disconnected-state"><PlugZap size={24} /><div><h2>Connect the control plane</h2><p>Authenticate with a project API key to load executions, budgets, incidents, and provider usage.</p></div><button className="primary-button" onClick={() => setConnectionOpen(true)} type="button">Connect API</button></section> : renderView()}</main></div>
    <ConnectionDialog connection={data.connection} error={data.error} loading={data.loading} mode={data.mode} onClose={() => setConnectionOpen(false)} onConnect={data.connect} onDisconnect={data.disconnect} open={connectionOpen} />
  </div>;
}
