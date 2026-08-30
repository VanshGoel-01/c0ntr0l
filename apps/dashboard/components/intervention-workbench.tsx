"use client";

import { useMemo, useState } from "react";
import { ArrowRight, ArrowUpRight, Ban, Check, FileClock, RotateCcw, Route, SearchX, ShieldCheck, Square } from "lucide-react";

import type { ModelPolicy, ModelTarget, RuntimeIntervention, RuntimeRecoveryRequest, RuntimeRecoveryResult } from "@/lib/types";

type InterventionWorkbenchProps = {
  intervention: RuntimeIntervention;
  modelPolicies: Record<string, ModelPolicy>;
  modelTargets: ModelTarget[];
  onOpenExecution: (executionId: string) => Promise<void>;
  onRecover: (request: RuntimeRecoveryRequest) => Promise<RuntimeRecoveryResult>;
};

type EvidenceMetric = { label: string; value: string };

const stages = [
  { label: "Detected", icon: SearchX },
  { label: "Blocked", icon: Ban },
  { label: "Understood", icon: ShieldCheck },
  { label: "Checkpointed", icon: FileClock },
  { label: "Recovery ready", icon: Route },
];

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function metricValue(value: unknown, fallback = "Not recorded"): string {
  if (typeof value === "number") return value.toLocaleString();
  if (typeof value === "boolean") return value ? "Confirmed" : "Not confirmed";
  if (typeof value === "string" && value.trim()) return value;
  return fallback;
}

function interventionMetrics(intervention: RuntimeIntervention): EvidenceMetric[] {
  const evidence = intervention.evidence;
  if (intervention.policyCode === "chat_model_policy") {
    return [
      { label: "Provider", value: metricValue(evidence.provider) },
      { label: "Model", value: metricValue(evidence.model) },
      { label: "Projected tokens", value: metricValue(evidence.projected_tokens) },
      { label: "Call limit", value: evidence.token_limit === null ? "Model disabled" : metricValue(evidence.token_limit) },
    ];
  }
  if (intervention.policyCode === "model_preflight") {
    return [
      { label: "Input tokens", value: metricValue(evidence.input_tokens) },
      { label: "Reserved output", value: metricValue(evidence.reserved_output_tokens) },
      { label: "Projected context", value: metricValue(evidence.projected_context_tokens) },
      { label: "Context window", value: metricValue(evidence.context_window_tokens) },
    ];
  }
  if (intervention.policyCode === "no_progress_loop") {
    return [
      { label: "Repeated calls", value: metricValue(evidence.occurrence, "0") },
      { label: "Allowed limit", value: metricValue(evidence.threshold, "0") },
      { label: "No-progress results", value: metricValue(evidence.no_progress_repeats, "0") },
      { label: "Identical output", value: metricValue(evidence.identical_results) },
    ];
  }
  return [
    { label: "Policy", value: intervention.policyCode.replaceAll("_", " ") },
    { label: "Mode", value: intervention.policyMode },
    { label: "Outcome", value: intervention.outcome },
    { label: "Execution", value: intervention.executionStatus },
  ];
}

function interventionSummary(policyCode: string): string {
  if (policyCode === "chat_model_policy") return "The gateway rejected the model request before opening a provider connection.";
  if (policyCode === "model_preflight") return "Context, model, or budget admission stopped the call before provider invocation.";
  if (policyCode === "no_progress_loop") return "The repeated operation was rejected before another tool or model call could run.";
  return "The execution was stopped before additional resources were consumed.";
}

export function InterventionWorkbench({ intervention, modelPolicies, modelTargets, onOpenExecution, onRecover }: InterventionWorkbenchProps) {
  const checkpoint = intervention.checkpoint;
  const failedOperation = asRecord(checkpoint?.packet.failedOperation);
  const failedArguments = asRecord(failedOperation.arguments);
  const initialQuery = typeof failedArguments.query === "string" ? failedArguments.query : "";
  const modificationKey = initialQuery ? "query" : "instruction";
  const [modifiedValue, setModifiedValue] = useState(initialQuery);
  const [selectedTarget, setSelectedTarget] = useState("");
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<RuntimeRecoveryResult | null>(null);
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const sourcePolicy = checkpoint ? modelPolicies[`${checkpoint.packet.sourceProvider}/${checkpoint.packet.sourceModel}`] : undefined;
  const sourceDisabled = intervention.policyCode === "chat_model_policy" && sourcePolicy?.mode === "block" && sourcePolicy.tokenLimit === null;
  const availableTargets = useMemo(() => modelTargets.filter((target) => {
    if (target.model === checkpoint?.packet.sourceModel && target.provider === checkpoint?.packet.sourceProvider) return false;
    const policy = modelPolicies[`${target.provider}/${target.model}`];
    return !(policy?.mode === "block" && policy.tokenLimit === null);
  }), [checkpoint?.packet.sourceModel, checkpoint?.packet.sourceProvider, modelPolicies, modelTargets]);
  const isConsumed = checkpoint?.status === "consumed";
  const metrics = interventionMetrics(intervention);
  const changedValue = modifiedValue.trim();
  const canRetry = changedValue.length > 0 && (!initialQuery || changedValue !== initialQuery.trim());

  async function recover(request: RuntimeRecoveryRequest) {
    setPending(true);
    setFeedback(null);
    setResult(null);
    try {
      const recovered = await onRecover(request);
      setResult(recovered);
      const execution = recovered.resumedExecutionId ? ` Linked execution ${recovered.resumedExecutionId.slice(0, 8)}.` : "";
      const usage = recovered.completion ? ` ${recovered.completion.totalTokens.toLocaleString()} tokens recorded.` : "";
      setFeedback({ kind: recovered.status === "failed" || recovered.status === "blocked" ? "error" : "success", text: `${recovered.message}${execution}${usage}` });
    } catch (caught) {
      setFeedback({ kind: "error", text: (caught as Error).message });
    } finally {
      setPending(false);
    }
  }

  return <section className="intervention-workbench panel">
    <header className="intervention-heading"><div><span className="section-kicker">Runtime intervention</span><h2>{intervention.reason}</h2><p>{new Date(intervention.decidedAt).toLocaleString()} · Policy {intervention.policyCode.replaceAll("_", " ")}</p></div><div className="intervention-outcome"><Ban size={18} /><span>{intervention.outcome}</span></div></header>
    <div className="recovery-flow" aria-label="Recoverable runtime enforcement stages">{stages.map(({ label, icon: Icon }, index) => <div className="recovery-stage" key={label}><span><Icon size={16} /></span><strong>{label}</strong>{index < stages.length - 1 && <ArrowRight aria-hidden="true" size={15} />}</div>)}</div>
    <div className="intervention-layout">
      <section className="intervention-evidence"><h3>Why c0ntr0l intervened</h3><dl>{metrics.map((metric) => <div key={metric.label}><dt>{metric.label}</dt><dd>{metric.value}</dd></div>)}</dl><p>{interventionSummary(intervention.policyCode)}</p></section>
      <section className="checkpoint-summary"><div className="section-title-row"><div><h3>Continuity checkpoint</h3><p>{checkpoint ? `Created ${new Date(checkpoint.createdAt).toLocaleString()}` : "Checkpoint unavailable"}</p></div>{checkpoint && <code>{checkpoint.contentFingerprint.slice(0, 12)}</code>}</div>{checkpoint ? <><h4>Task</h4><p>{checkpoint.packet.task}</p><h4>Completed work</h4>{checkpoint.packet.completedWork.length ? <ul>{checkpoint.packet.completedWork.map((item) => <li key={item}><Check size={14} />{item}</li>)}</ul> : <p>No completed progress was reported before intervention.</p>}<h4>Failed operation</h4><pre>{JSON.stringify(checkpoint.packet.failedOperation, null, 2)}</pre><h4>Recommended action</h4><p>{checkpoint.packet.recommendedAction}</p></> : <p>This execution was blocked before a checkpoint could be stored.</p>}</section>
      <section className="recovery-controls"><h3>Continue safely</h3><p>Recovery creates a linked execution and keeps this source trace unchanged for audit.</p><label><span>{initialQuery ? "Modified query" : "Recovery instruction"}</span><input disabled={pending || isConsumed || sourceDisabled} onChange={(event) => setModifiedValue(event.target.value)} placeholder={initialQuery ? "Enter a different query" : "Describe how the task should continue"} value={modifiedValue} /></label>{sourceDisabled && <p className="recovery-notice">The source model is disabled. Change its policy or choose a fallback model.</p>}<button className="recovery-command" disabled={pending || isConsumed || sourceDisabled || !canRetry} onClick={() => void recover({ strategy: "retry_modified", modifiedArguments: { [modificationKey]: changedValue } })} type="button"><RotateCcw size={16} /><span><strong>Retry current model</strong><small>Run the checkpoint with corrected arguments or instructions</small></span></button><label><span>Handoff model</span><select disabled={pending || isConsumed || !availableTargets.length} onChange={(event) => setSelectedTarget(event.target.value)} value={selectedTarget}><option value="">Select an operational model</option>{availableTargets.map((target) => <option key={`${target.provider}:${target.model}`} value={`${target.provider}::${target.model}`}>{target.provider} · {target.model}</option>)}</select></label><button className="recovery-command" disabled={pending || isConsumed || !selectedTarget} onClick={() => { const [targetProvider, targetModel] = selectedTarget.split("::"); void recover({ strategy: "model_handoff", targetProvider, targetModel }); }} type="button"><Route size={16} /><span><strong>Continue on model</strong><small>Execute the verified packet through an allowed fallback</small></span></button><div className="recovery-secondary"><button disabled={pending || isConsumed} onClick={() => void recover({ strategy: "manual_resume" })} type="button"><FileClock size={15} />Manual resume</button><button disabled={pending || isConsumed} onClick={() => void recover({ strategy: "stop" })} type="button"><Square size={15} />Keep stopped</button></div>{isConsumed && !feedback && <p className="recovery-feedback success">This checkpoint has already been consumed by a recovery.</p>}{feedback && <p className={`recovery-feedback ${feedback.kind}`}>{feedback.text}</p>}{result?.completion?.content && <div className="recovery-output"><span>Recovered output</span><p>{result.completion.content}</p></div>}{result?.resumedExecutionId && <button className="open-resumed" onClick={() => void onOpenExecution(result.resumedExecutionId as string)} type="button"><ArrowUpRight size={15} />Open resumed trace</button>}</section>
    </div>
  </section>;
}
