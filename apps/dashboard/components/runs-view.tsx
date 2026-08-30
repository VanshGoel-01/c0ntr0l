"use client";

import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";

import { ExecutionTable } from "@/components/execution-table";
import { TraceDetails } from "@/components/trace-details";
import { deriveRisk } from "@/lib/metrics";
import type { ConsoleSettings, Execution, ExecutionDetail, ModelPolicy, ModelTarget, RuntimeIntervention, RuntimeRecoveryRequest, RuntimeRecoveryResult } from "@/lib/types";

type RunsViewProps = {
  executions: Execution[];
  settings: ConsoleSettings;
  requestedExecution: Execution | null;
  loadExecution: (id: string) => Promise<ExecutionDetail | null>;
  loadIntervention: (id: string) => Promise<RuntimeIntervention | null>;
  modelPolicies: Record<string, ModelPolicy>;
  modelTargets: ModelTarget[];
  recoverExecution: (id: string, request: RuntimeRecoveryRequest) => Promise<RuntimeRecoveryResult>;
  cancelExecution: (id: string) => Promise<unknown>;
  onSelectionHandled: () => void;
};

export function RunsView({ executions, settings, requestedExecution, loadExecution, loadIntervention, modelPolicies, modelTargets, recoverExecution, cancelExecution, onSelectionHandled }: RunsViewProps) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [risk, setRisk] = useState("all");
  const [detail, setDetail] = useState<ExecutionDetail | null>(null);
  const [intervention, setIntervention] = useState<RuntimeIntervention | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const filtered = useMemo(() => executions.filter((run) => {
    const runRisk = deriveRisk(run, settings).level;
    const haystack = `${run.traceId} ${run.project} ${run.application} ${run.model} ${run.provider} ${run.errorCode ?? ""}`.toLowerCase();
    return (status === "all" || run.status === status) && (risk === "all" || runRisk === risk) && haystack.includes(query.trim().toLowerCase());
  }), [executions, query, risk, settings, status]);
  async function openExecution(executionId: string) {
    setLoading(true); setLoadError(null);
    try {
      const [nextDetail, nextIntervention] = await Promise.all([loadExecution(executionId), loadIntervention(executionId)]);
      setDetail(nextDetail);
      setIntervention(nextIntervention);
    } catch (caught) { setLoadError((caught as Error).message); } finally { setLoading(false); }
  }

  async function openRun(run: Execution) {
    await openExecution(run.id);
  }

  async function recover(request: RuntimeRecoveryRequest): Promise<RuntimeRecoveryResult> {
    if (!detail) throw new Error("No execution is selected.");
    const result = await recoverExecution(detail.id, request);
    const [nextDetail, nextIntervention] = await Promise.all([loadExecution(detail.id), loadIntervention(detail.id)]);
    setDetail(nextDetail);
    setIntervention(nextIntervention);
    return result;
  }

  async function cancel() {
    if (!detail) return;
    await cancelExecution(detail.id);
  }

  useEffect(() => {
    if (!requestedExecution) return;
    void openRun(requestedExecution);
    onSelectionHandled();
  }, [requestedExecution]); // eslint-disable-line react-hooks/exhaustive-deps

  if (detail) return <TraceDetails detail={detail} intervention={intervention} modelPolicies={modelPolicies} modelTargets={modelTargets} onBack={() => { setDetail(null); setIntervention(null); }} onCancel={cancel} onOpenExecution={openExecution} onRecover={recover} settings={settings} />;
  return <div className="module-view view-enter"><div className="page-intro"><div><h2>Executions</h2><p>Inspect requests across projects, applications, models, usage, latency, and runtime risk.</p></div><span className="count-badge">{filtered.length} results</span></div>
    <section className="panel execution-panel"><div className="filterbar"><label className="search-control"><Search size={16} /><input aria-label="Search executions" onChange={(event) => setQuery(event.target.value)} placeholder="Trace, application, model, or error" value={query} /></label><select aria-label="Filter by status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">All statuses</option><option value="running">Running</option><option value="completed">Completed</option><option value="failed">Failed</option><option value="blocked">Blocked</option></select><select aria-label="Filter by risk" value={risk} onChange={(event) => setRisk(event.target.value)}><option value="all">All risk</option><option value="critical">Critical</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></div>{loading && <div className="loading-row">Loading trace details...</div>}{loadError && <div className="error-row">{loadError}</div>}<ExecutionTable executions={filtered} onOpen={(run) => void openRun(run)} settings={settings} /></section>
  </div>;
}
