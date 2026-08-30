"use client";

import { useMemo, useState } from "react";
import { ArrowRight, Ban, Check, FileClock, RotateCcw, Route, SearchX, ShieldCheck, Square } from "lucide-react";

import type { ModelTarget, RuntimeIntervention, RuntimeRecoveryRequest, RuntimeRecoveryResult } from "@/lib/types";

type InterventionWorkbenchProps = {
  intervention: RuntimeIntervention;
  modelTargets: ModelTarget[];
  onRecover: (request: RuntimeRecoveryRequest) => Promise<RuntimeRecoveryResult>;
};

const stages = [
  { label: "Detected", icon: SearchX },
  { label: "Blocked", icon: Ban },
  { label: "Understood", icon: ShieldCheck },
  { label: "Checkpointed", icon: FileClock },
  { label: "Recovery ready", icon: Route },
];

export function InterventionWorkbench({ intervention, modelTargets, onRecover }: InterventionWorkbenchProps) {
  const checkpoint = intervention.checkpoint;
  const failedArguments = checkpoint?.packet.failedOperation.arguments;
  const initialQuery = typeof failedArguments === "object" && failedArguments !== null && "query" in failedArguments
    ? String((failedArguments as Record<string, unknown>).query ?? "")
    : "";
  const [modifiedQuery, setModifiedQuery] = useState(initialQuery);
  const [selectedTarget, setSelectedTarget] = useState("");
  const [pending, setPending] = useState(false);
  const [feedback, setFeedback] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const availableTargets = useMemo(() => modelTargets.filter((target) => target.model !== checkpoint?.packet.sourceModel || target.provider !== checkpoint?.packet.sourceProvider), [checkpoint?.packet.sourceModel, checkpoint?.packet.sourceProvider, modelTargets]);
  const isConsumed = checkpoint?.status === "consumed";

  async function recover(request: RuntimeRecoveryRequest) {
    setPending(true);
    setFeedback(null);
    try {
      const result = await onRecover(request);
      const execution = result.resumedExecutionId ? ` Execution ${result.resumedExecutionId.slice(0, 8)}.` : "";
      const usage = result.completion ? ` ${result.completion.totalTokens.toLocaleString()} tokens recorded.` : "";
      setFeedback({ kind: result.status === "failed" ? "error" : "success", text: `${result.message}${execution}${usage}` });
    } catch (caught) {
      setFeedback({ kind: "error", text: (caught as Error).message });
    } finally {
      setPending(false);
    }
  }

  const evidence = intervention.evidence;
  const observed = Number(evidence.occurrence ?? 0);
  const threshold = Number(evidence.threshold ?? 0);
  const noProgress = Number(evidence.no_progress_repeats ?? 0);

  return <section className="intervention-workbench panel">
    <header className="intervention-heading"><div><span className="section-kicker">Runtime intervention</span><h2>{intervention.reason}</h2><p>{new Date(intervention.decidedAt).toLocaleString()} · Policy {intervention.policyCode.replaceAll("_", " ")}</p></div><div className="intervention-outcome"><Ban size={18} /><span>{intervention.outcome}</span></div></header>
    <div className="recovery-flow" aria-label="Recoverable runtime enforcement stages">{stages.map(({ label, icon: Icon }, index) => <div className="recovery-stage" key={label}><span><Icon size={16} /></span><strong>{label}</strong>{index < stages.length - 1 && <ArrowRight aria-hidden="true" size={15} />}</div>)}</div>
    <div className="intervention-layout">
      <section className="intervention-evidence"><h3>Why c0ntr0l intervened</h3><dl><div><dt>Repeated calls</dt><dd>{observed}</dd></div><div><dt>Allowed limit</dt><dd>{threshold}</dd></div><div><dt>No-progress results</dt><dd>{noProgress}</dd></div><div><dt>Identical output</dt><dd>{evidence.identical_results ? "Confirmed" : "Not confirmed"}</dd></div></dl><p>The proposed action was rejected before it reached the tool or model provider.</p></section>
      <section className="checkpoint-summary"><div className="section-title-row"><div><h3>Continuity checkpoint</h3><p>{checkpoint ? `Created ${new Date(checkpoint.createdAt).toLocaleString()}` : "Checkpoint unavailable"}</p></div>{checkpoint && <code>{checkpoint.contentFingerprint.slice(0, 12)}</code>}</div>{checkpoint ? <><h4>Task</h4><p>{checkpoint.packet.task}</p><h4>Completed work</h4>{checkpoint.packet.completedWork.length ? <ul>{checkpoint.packet.completedWork.map((item) => <li key={item}><Check size={14} />{item}</li>)}</ul> : <p>No completed progress was reported before intervention.</p>}<h4>Failed operation</h4><pre>{JSON.stringify(checkpoint.packet.failedOperation, null, 2)}</pre><h4>Recommended action</h4><p>{checkpoint.packet.recommendedAction}</p></> : <p>This execution was blocked before a checkpoint could be stored.</p>}</section>
      <section className="recovery-controls"><h3>Continue safely</h3><p>Recovery creates a linked execution and keeps this failed run unchanged for audit.</p><label><span>Modified query</span><input disabled={pending || isConsumed} onChange={(event) => setModifiedQuery(event.target.value)} value={modifiedQuery} /></label><button className="recovery-command" disabled={pending || isConsumed || modifiedQuery.trim() === initialQuery.trim() || !modifiedQuery.trim()} onClick={() => void recover({ strategy: "retry_modified", modifiedArguments: { query: modifiedQuery.trim() } })} type="button"><RotateCcw size={16} /><span><strong>Retry modified</strong><small>Run corrected arguments on the current configured provider</small></span></button><label><span>Handoff model</span><select disabled={pending || isConsumed || !availableTargets.length} onChange={(event) => setSelectedTarget(event.target.value)} value={selectedTarget}><option value="">Select an observed model</option>{availableTargets.map((target) => <option key={`${target.provider}:${target.model}`} value={`${target.provider}::${target.model}`}>{target.provider} · {target.model}</option>)}</select></label><button className="recovery-command" disabled={pending || isConsumed || !selectedTarget} onClick={() => { const [targetProvider, targetModel] = selectedTarget.split("::"); void recover({ strategy: "model_handoff", targetProvider, targetModel }); }} type="button"><Route size={16} /><span><strong>Continue on model</strong><small>Execute the verified packet through a configured fallback</small></span></button><div className="recovery-secondary"><button disabled={pending || isConsumed} onClick={() => void recover({ strategy: "manual_resume" })} type="button"><FileClock size={15} />Manual resume</button><button disabled={pending || isConsumed} onClick={() => void recover({ strategy: "stop" })} type="button"><Square size={15} />Keep stopped</button></div>{isConsumed && <p className="recovery-feedback success">This checkpoint has already been consumed by a recovery.</p>}{feedback && <p className={`recovery-feedback ${feedback.kind}`}>{feedback.text}</p>}</section>
    </div>
  </section>;
}
