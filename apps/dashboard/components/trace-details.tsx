"use client";

import { useMemo, useState } from "react";
import { ArrowLeft, Braces, Download, GitBranch, ShieldAlert, Square, Timer, Wrench } from "lucide-react";

import { InterventionWorkbench } from "@/components/intervention-workbench";
import { deriveRisk, formatDuration } from "@/lib/metrics";
import type { ConsoleSettings, ExecutionDetail, ModelTarget, RuntimeIntervention, RuntimeRecoveryRequest, RuntimeRecoveryResult } from "@/lib/types";

type TraceDetailsProps = {
  detail: ExecutionDetail;
  settings: ConsoleSettings;
  intervention: RuntimeIntervention | null;
  modelTargets: ModelTarget[];
  onBack: () => void;
  onCancel: () => Promise<void>;
  onRecover: (request: RuntimeRecoveryRequest) => Promise<RuntimeRecoveryResult>;
};

export function TraceDetails({ detail, settings, intervention, modelTargets, onBack, onCancel, onRecover }: TraceDetailsProps) {
  const [selectedId, setSelectedId] = useState(detail.spans.find((span) => span.status === "blocked" || span.status === "failed")?.id ?? detail.spans[0]?.id);
  const [cancelState, setCancelState] = useState<"idle" | "pending" | "failed">("idle");
  const selected = detail.spans.find((span) => span.id === selectedId) ?? detail.spans[0];
  const risk = deriveRisk(detail, settings);
  const repeatCount = Number(detail.metadata.repeat_count ?? selected?.attributes.repeat_count ?? 0);
  const repeatThreshold = Number(detail.metadata.repeat_threshold ?? settings.repeatThreshold);
  const toolCalls = detail.spans.filter((span) => span.kind === "tool").length || Number(detail.metadata.tool_calls ?? 0);
  const errors = detail.spans.filter((span) => span.status === "failed" || span.status === "blocked").length;
  const children = useMemo(() => new Set(detail.spans.map((span) => span.parentSpanId).filter(Boolean)), [detail.spans]);

  function exportTrace() {
    const blob = new Blob([JSON.stringify({ ...detail, intervention }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${detail.traceId}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function cancel() {
    setCancelState("pending");
    try {
      await onCancel();
      onBack();
    } catch {
      setCancelState("failed");
    }
  }

  return <div className="trace-view view-enter">
    <div className="trace-titlebar"><button className="back-button" onClick={onBack} type="button"><ArrowLeft size={16} />Back to runs</button><div className="trace-actions">{detail.status === "running" && <button className="danger-button" disabled={cancelState === "pending"} onClick={() => void cancel()} type="button"><Square size={14} />{cancelState === "pending" ? "Cancelling" : "Cancel run"}</button>}<button className="secondary-button" onClick={exportTrace} type="button"><Download size={15} />Export JSON</button></div></div>
    {cancelState === "failed" && <div className="runtime-banner">The cancellation request failed. The execution state was not changed.</div>}
    <section className="trace-header panel"><div><span>Trace ID</span><strong>{detail.traceId}</strong></div><div><span>Project</span><strong>{detail.project}</strong></div><div><span>Application</span><strong>{detail.application}</strong></div><div><span>Status</span><strong><span className="status-pill" data-status={detail.status}>{detail.status}</span></strong></div><div><span>Trigger</span><strong>{risk.reason}</strong></div><div><span>Duration</span><strong>{formatDuration(detail.durationMs)}</strong></div></section>
    <div className="trace-workbench">
      <section className="trace-column panel"><div className="panel-heading"><div><h2>Execution tree</h2><p>{detail.spans.length} recorded spans</p></div><GitBranch size={18} /></div><div className="execution-tree">{detail.spans.map((span) => <button className="tree-span" data-selected={selected?.id === span.id} key={span.id} onClick={() => setSelectedId(span.id)} style={{ paddingLeft: span.parentSpanId ? "30px" : "12px" }} type="button"><span className="span-node" data-kind={span.kind} data-status={span.status}>{span.kind === "tool" ? <Wrench size={11} /> : span.kind === "policy" ? <ShieldAlert size={11} /> : <Braces size={11} />}</span><div><strong>{span.name}</strong><small>{span.toolName ?? span.kind}</small></div><code>{formatDuration(span.durationMs)}</code>{children.has(span.id) && <i />}</button>)}</div></section>
      <section className="span-column panel">{selected ? <><div className="panel-heading"><div><h2>{selected.name}</h2><p>{selected.kind} span</p></div><span className="status-pill" data-status={selected.status}>{selected.status}</span></div><dl className="span-fields"><div><dt>Span ID</dt><dd><code>{selected.id}</code></dd></div><div><dt>Parent</dt><dd><code>{selected.parentSpanId ?? "Root"}</code></dd></div><div><dt>Tool</dt><dd>{selected.toolName ?? "None"}</dd></div><div><dt>Duration</dt><dd>{formatDuration(selected.durationMs)}</dd></div><div><dt>Error</dt><dd>{selected.errorCode ?? "None"}</dd></div></dl><div className="attribute-block"><h3>Evidence</h3>{Object.keys(selected.attributes).length ? Object.entries(selected.attributes).map(([key, value]) => <div key={key}><span>{key.replaceAll("_", " ")}</span><code>{typeof value === "object" ? JSON.stringify(value) : String(value)}</code></div>) : <p>No sanitized attributes were recorded for this span.</p>}</div><div className="event-list"><h3>Events</h3><div><time>{new Date(selected.startedAt).toLocaleTimeString()}</time><span>Span started</span></div>{selected.completedAt && <div><time>{new Date(selected.completedAt).toLocaleTimeString()}</time><span>Span {selected.status}</span></div>}{selected.errorCode && <div data-error="true"><time>{new Date(selected.completedAt ?? selected.startedAt).toLocaleTimeString()}</time><span>{selected.errorCode.replaceAll("_", " ")}</span></div>}</div></> : <p>No span selected.</p>}</section>
      <aside className="summary-column panel"><div className="panel-heading"><div><h2>Trace summary</h2><p>Runtime totals</p></div><Timer size={18} /></div><dl className="summary-list"><div><dt>Total cost</dt><dd>${detail.totalCost.toFixed(4)}</dd></div><div><dt>Total tokens</dt><dd>{detail.totalTokens.toLocaleString()}</dd></div><div><dt>Total spans</dt><dd>{detail.spans.length}</dd></div><div><dt>Model calls</dt><dd>{detail.usage.length || detail.spans.filter((span) => span.kind === "provider").length}</dd></div><div><dt>Tool calls</dt><dd>{toolCalls}</dd></div><div><dt>Errors</dt><dd>{errors}</dd></div></dl><div className="policy-summary"><h3>Policy result</h3><div><span>Risk</span><b className="risk-pill" data-risk={risk.level}>{risk.level}</b></div><div><span>Repeat limit</span><b>{repeatThreshold}</b></div><div><span>Observed</span><b>{repeatCount || "None"}</b></div><p>{intervention ? intervention.reason : detail.status === "blocked" ? "Execution stopped before additional resources were consumed." : "No blocking policy ended this execution."}</p></div></aside>
    </div>
    {intervention && <InterventionWorkbench intervention={intervention} modelTargets={modelTargets} onRecover={onRecover} />}
  </div>;
}
