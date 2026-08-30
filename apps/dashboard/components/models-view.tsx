"use client";

import { RefreshCw, ShieldCheck } from "lucide-react";

import { ModelLogo } from "@/components/model-logo";
import { useProviderStatus } from "@/hooks/use-provider-status";
import { deriveModelStats, formatDuration, formatTokens } from "@/lib/metrics";
import type { ConnectionConfig, Execution, ModelPolicy, PolicyMode } from "@/lib/types";

type ModelsViewProps = {
  connection: ConnectionConfig | null;
  error: string | null;
  executions: Execution[];
  loadingPolicies: boolean;
  policies: Record<string, ModelPolicy>;
  savingKeys: Set<string>;
  onMode: (provider: string, model: string, mode: PolicyMode) => Promise<void>;
  onLimit: (provider: string, model: string, limit: number | null) => Promise<void>;
};

export function ModelsView({ connection, error, executions, loadingPolicies, policies, savingKeys, onMode, onLimit }: ModelsViewProps) {
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
    <section className="panel model-table-panel"><div className="panel-heading"><div><h2>Model policies</h2><p>Project rules are stored by the control plane and checked during runtime execution preflight.</p></div><span className="policy-seal"><ShieldCheck size={15} />{loadingPolicies ? "Loading rules" : "Preflight active"}</span></div>{error && <div className="error-row">Policy save failed: {error}</div>}<div className="table-scroll"><table className="model-table"><thead><tr><th>Provider</th><th>Model</th><th>Runs</th><th>Tokens</th><th>Per-call limit</th><th>Latency</th><th>Policy mode</th></tr></thead><tbody>{models.map((model) => { const policy = policies[model.key] ?? { mode: "observe" as PolicyMode, tokenLimit: null }; const saving = savingKeys.has(model.key); const limitLabel = policy.tokenLimit !== null ? `${formatTokens(policy.tokenLimit)} max` : policy.mode === "block" ? "Model disabled" : policy.mode === "warn" ? "Warn every call" : "All request sizes"; return <tr key={model.key}><td>{model.provider}</td><td><div className="model-identity"><ModelLogo model={model.model} provider={model.provider} /><div><strong>{model.model}</strong><small>{saving ? "Saving policy" : `${model.active} active / ${model.completed} completed`}</small></div></div></td><td>{model.runs}</td><td>{formatTokens(model.tokens)}</td><td><label className="token-limit"><input aria-label={`${model.model} per-call token limit`} defaultValue={policy.tokenLimit ?? ""} disabled={saving} key={`${model.key}-${policy.tokenLimit ?? "none"}`} min="1" onBlur={(event) => { const value = event.target.value ? Number(event.target.value) : null; if (value !== policy.tokenLimit) void onLimit(model.provider, model.model, value).catch(() => undefined); }} placeholder="No limit" type="number" /><span>{limitLabel}</span></label></td><td>{formatDuration(model.averageLatencyMs)}</td><td><div className="policy-control" role="group" aria-label={`${model.model} policy mode`}>{(["observe", "warn", "block"] as PolicyMode[]).map((mode) => <button data-active={policy.mode === mode} disabled={saving} key={mode} onClick={() => void onMode(model.provider, model.model, mode).catch(() => undefined)} type="button">{mode}</button>)}</div></td></tr>; })}</tbody></table></div></section>
  </div>;
}
