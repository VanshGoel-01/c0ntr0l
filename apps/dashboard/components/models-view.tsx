"use client";

import { RefreshCw, ShieldCheck } from "lucide-react";

import { ModelLogo } from "@/components/model-logo";
import { useProviderStatus } from "@/hooks/use-provider-status";
import { deriveModelStats, formatDuration, formatTokens } from "@/lib/metrics";
import type { ConnectionConfig, Execution, ModelPolicy, PolicyMode } from "@/lib/types";

export function ModelsView({ connection, executions, policies, onMode, onLimit }: { connection: ConnectionConfig | null; executions: Execution[]; policies: Record<string, ModelPolicy>; onMode: (key: string, mode: PolicyMode) => void; onLimit: (key: string, limit: number | null) => void }) {
  const { status, loading, refresh } = useProviderStatus(connection);
  const models = deriveModelStats(executions);
  const providerCards = (status?.providers ?? []).map((provider) => ({
    name: provider.name.charAt(0).toUpperCase() + provider.name.slice(1),
    state: provider.status === "operational" ? "Operational" : "Offline",
    detail: provider.status === "operational" ? `${provider.models.length} installed` : "Provider unavailable",
    models: provider.models,
  }));
  return <div className="module-view view-enter"><div className="page-intro"><div><h2>Models</h2><p>Runtime health, observed usage, token limits, and response policy for zero-cost routes.</p></div><button className="secondary-button" disabled={loading} onClick={() => void refresh()} type="button"><RefreshCw className={loading ? "spin" : undefined} size={15} />Recheck</button></div>
    <section className="provider-cards">{providerCards.map((provider) => <article key={provider.name}><ModelLogo provider={provider.name} size={42} /><div><h3>{provider.name}</h3><span className="provider-health" data-state={provider.state.toLowerCase()}><i />{provider.state}</span></div><strong>{provider.detail}</strong>{provider.models.length > 0 && <small className="provider-models">{provider.models.join(" · ")}</small>}</article>)}{connection && !loading && providerCards.length === 0 && <p>No routable providers reported.</p>}</section>
    <section className="panel model-table-panel"><div className="panel-heading"><div><h2>Model review rules</h2><p>Live usage with browser-local review thresholds. Enforced limits remain visible on the Budgets page.</p></div><span className="policy-seal"><ShieldCheck size={15} />No paid routes</span></div><div className="table-scroll"><table className="model-table"><thead><tr><th>Provider</th><th>Model</th><th>Runs</th><th>Tokens</th><th>Review limit</th><th>Latency</th><th>Review mode</th></tr></thead><tbody>{models.map((model) => { const policy = policies[model.key] ?? { mode: "observe" as PolicyMode, tokenLimit: null }; const left = policy.tokenLimit === null ? null : Math.max(0, policy.tokenLimit - model.tokens); return <tr key={model.key}><td>{model.provider}</td><td><div className="model-identity"><ModelLogo model={model.model} provider={model.provider} /><div><strong>{model.model}</strong><small>{model.active} active / {model.completed} completed</small></div></div></td><td>{model.runs}</td><td>{formatTokens(model.tokens)}</td><td><label className="token-limit"><input aria-label={`${model.model} review token limit`} min="0" onChange={(event) => onLimit(model.key, event.target.value ? Number(event.target.value) : null)} placeholder="No limit" type="number" value={policy.tokenLimit ?? ""} /><span>{left === null ? "Unlimited" : `${formatTokens(left)} left`}</span></label></td><td>{formatDuration(model.averageLatencyMs)}</td><td><div className="policy-control" role="group" aria-label={`${model.model} review mode`}>{(["observe", "warn", "block"] as PolicyMode[]).map((mode) => <button data-active={policy.mode === mode} key={mode} onClick={() => onMode(model.key, mode)} type="button">{mode}</button>)}</div></td></tr>; })}</tbody></table></div></section>
  </div>;
}
