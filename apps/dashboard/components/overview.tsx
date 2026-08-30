"use client";

import { useState } from "react";
import { Activity, ArrowRight, CircleCheck, CircleGauge, ShieldAlert, X } from "lucide-react";

import { ExecutionTable } from "@/components/execution-table";
import { ModelLogo } from "@/components/model-logo";
import { UsageChart } from "@/components/usage-chart";
import {
  deriveActivityChart,
  deriveApplicationStats,
  deriveMetrics,
  deriveModelStats,
  formatDuration,
  formatTokens,
} from "@/lib/metrics";
import type { ConsoleSettings, Execution, Incident, ModelPolicy, WorkspaceContext } from "@/lib/types";

type OverviewProps = {
  executions: Execution[];
  workspace: WorkspaceContext;
  settings: ConsoleSettings;
  incidents: Incident[];
  modelPolicies: Record<string, ModelPolicy>;
  onViewRuns: () => void;
  onViewIncidents: () => void;
  onViewModels: () => void;
  onOpenRun: (run: Execution) => void;
};

export function Overview(props: OverviewProps) {
  const [selectedApplication, setSelectedApplication] = useState<string | null>(null);
  const summary = deriveMetrics(props.executions);
  const models = deriveModelStats(props.executions);
  const openIncidents = props.incidents.filter((incident) => incident.status !== "resolved");
  const applications = deriveApplicationStats(props.executions, props.incidents);
  const tokenLimit = props.workspace.budgets.find((budget) => budget.isEnabled && budget.maxTokens)?.maxTokens ?? null;
  const tokenPercent = tokenLimit ? Math.min(100, (props.workspace.tokens24h / tokenLimit) * 100) : null;
  const activeRuns = props.executions.filter((run) => run.status === "running" || run.status === "accepted");
  const tableRuns = activeRuns.length ? activeRuns : props.executions.slice(0, 4);
  const selected = applications.find((application) => application.name === selectedApplication);

  return <div className="overview-view view-enter">
    <section className="metric-strip" aria-label="Workspace summary">
      <article><span className="metric-icon indigo"><CircleCheck size={18} /></span><div><span>Success rate</span><strong>{summary.successRate.toFixed(1)}%</strong><small>{summary.completed} of {summary.terminal} finished runs</small></div></article>
      <article><span className="metric-icon blue"><Activity size={18} /></span><div><span>Active runs</span><strong>{summary.active}</strong><small>{summary.p95LatencyMs === null ? "No latency sample" : `${formatDuration(summary.p95LatencyMs)} p95 latency`}</small></div></article>
      <article><span className="metric-icon cream"><CircleGauge size={18} /></span><div><span>Token budget</span><strong>{tokenPercent === null ? formatTokens(summary.tokens) : `${tokenPercent.toFixed(1)}%`}</strong><small>{tokenLimit ? `${formatTokens(props.workspace.tokens24h)} of ${formatTokens(tokenLimit)}` : "No token limit configured"}</small></div></article>
      <article><span className="metric-icon magenta"><ShieldAlert size={18} /></span><div><span>Open incidents</span><strong>{openIncidents.length}</strong><small>{openIncidents.filter((incident) => incident.severity === "critical").length} critical</small></div></article>
    </section>

    <div className="overview-primary"><UsageChart data={deriveActivityChart(props.executions)} />
      <section className="panel model-summary"><div className="panel-heading"><div><h2>Model controls</h2><p>Largest calls against per-call limits</p></div><button className="link-button" onClick={props.onViewModels} type="button">Manage <ArrowRight size={14} /></button></div>
        <div className="capacity-list">{models.slice(0, 4).map((model) => {
          const policy = props.modelPolicies[model.key];
          const largestCall = Math.max(0, ...props.executions.filter((run) => run.provider === model.provider && run.model === model.model).map((run) => run.totalTokens));
          const percent = policy?.tokenLimit ? Math.min(100, largestCall / policy.tokenLimit * 100) : null;
          return <button key={model.key} onClick={props.onViewModels} type="button"><div className="capacity-model"><ModelLogo model={model.model} provider={model.provider} /><div><strong>{model.model}</strong><span>{model.provider}</span></div></div><div className="capacity-values"><b>{formatTokens(largestCall)}</b><span>{policy?.tokenLimit ? `${formatTokens(policy.tokenLimit)} max` : "No limit"}</span></div><span className="progress-track"><i style={{ width: `${percent ?? 0}%` }} /></span></button>;
        })}</div>
      </section>
    </div>

    <section className="panel execution-panel"><div className="panel-heading"><div><h2>{activeRuns.length ? "Active executions" : "Recent executions"}</h2><p>Trace, application, model, usage, and risk</p></div><button className="link-button" onClick={props.onViewRuns} type="button">All runs <ArrowRight size={14} /></button></div><ExecutionTable executions={tableRuns} onOpen={props.onOpenRun} settings={props.settings} /></section>

    <div className="overview-secondary">
      <section className="panel application-panel"><div className="panel-heading"><div><h2>Application usage</h2><p>Zero-cost spend with token distribution</p></div></div><div className="application-list">{applications.slice(0, 5).map((application) => <button key={application.name} onClick={() => setSelectedApplication(application.name)} type="button"><div><strong>{application.name}</strong><span>{application.runs} runs / {application.active} active</span></div><div><b>{formatTokens(application.tokens)}</b><span>${application.cost.toFixed(2)} spend</span></div><i data-alert={application.incidents > 0}>{application.incidents}</i><ArrowRight size={15} /></button>)}</div></section>
      <section className="panel incident-snapshot"><div className="panel-heading"><div><h2>Incident queue</h2><p>Generated from execution evidence</p></div><button className="link-button" onClick={props.onViewIncidents} type="button">Open <ArrowRight size={14} /></button></div><div className="incident-mini-list">{openIncidents.slice(0, 4).map((incident) => <button key={incident.id} onClick={props.onViewIncidents} type="button"><span className="severity-mark" data-severity={incident.severity} /><div><strong>{incident.title}</strong><span>{incident.application} / {incident.model}</span></div><b>{incident.severity}</b></button>)}{openIncidents.length === 0 && <p className="empty-copy">No incidents in the selected range.</p>}</div></section>
    </div>

    {selected && <div className="dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setSelectedApplication(null)} role="presentation"><section className="dialog-panel application-detail" role="dialog" aria-modal="true" aria-labelledby="application-detail-title"><div className="dialog-heading"><div><span>Application</span><h2 id="application-detail-title">{selected.name}</h2></div><button className="icon-button" onClick={() => setSelectedApplication(null)} title="Close application details" type="button"><X size={17} /></button></div><div className="application-detail-grid"><div><span>Executions</span><strong>{selected.runs}</strong></div><div><span>Active</span><strong>{selected.active}</strong></div><div><span>Tokens</span><strong>{selected.tokens.toLocaleString()}</strong></div><div><span>Spend</span><strong>${selected.cost.toFixed(2)}</strong></div></div><h3>Model usage</h3>{selected.models.map((model) => <div className="model-breakdown" key={model.name}><strong>{model.name}</strong><span>{formatTokens(model.tokens)} tokens</span></div>)}</section></div>}
  </div>;
}
