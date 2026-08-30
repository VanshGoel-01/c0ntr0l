"use client";

import { useMemo } from "react";
import { RefreshCw, ShieldCheck } from "lucide-react";

import { ModelLogo } from "@/components/model-logo";
import { deriveModelStats, formatDuration, formatTokens } from "@/lib/metrics";
import type { Execution, ModelPolicy, PolicyMode, ProviderCatalog } from "@/lib/types";

type ModelsViewProps = {
  error: string | null;
  executions: Execution[];
  loadingPolicies: boolean;
  loadingProviders: boolean;
  providerCatalog: ProviderCatalog | null;
  providerError: string | null;
  policies: Record<string, ModelPolicy>;
  savingKeys: Set<string>;
  onRefreshProviders: () => Promise<void>;
  onMode: (provider: string, model: string, mode: PolicyMode) => Promise<void>;
  onLimit: (provider: string, model: string, limit: number | null) => Promise<void>;
};

export function ModelsView({ error, executions, loadingPolicies, loadingProviders, providerCatalog, providerError, policies, savingKeys, onRefreshProviders, onMode, onLimit }: ModelsViewProps) {
  const observedModels = useMemo(() => deriveModelStats(executions), [executions]);
  const models = useMemo(() => {
    const rows = new Map(observedModels.map((model) => [model.key, model]));
    for (const provider of providerCatalog?.providers ?? []) {
      for (const model of provider.models) {
        const key = `${provider.name}/${model}`;
        if (!rows.has(key)) {
          rows.set(key, {
            key,
            provider: provider.name,
            model,
            runs: 0,
            active: 0,
            completed: 0,
            tokens: 0,
            cost: 0,
            averageLatencyMs: null,
            lastUsedAt: "",
          });
        }
      }
    }
    return [...rows.values()].sort((left, right) => right.tokens - left.tokens || left.model.localeCompare(right.model));
  }, [observedModels, providerCatalog]);
  const providerCards = (providerCatalog?.providers ?? []).map((provider) => ({
    name: provider.name.charAt(0).toUpperCase() + provider.name.slice(1),
    state: provider.status === "operational" ? "Operational" : "Offline",
    detail: provider.status === "operational" ? `${provider.models.length} installed` : "Provider unavailable",
    models: provider.models,
  }));
  return <div className="module-view view-enter"><div className="page-intro"><div><h2>Models</h2><p>Runtime health, observed usage, token limits, and response policy for zero-cost routes.</p></div><button className="secondary-button" disabled={loadingProviders} onClick={() => void onRefreshProviders()} type="button"><RefreshCw className={loadingProviders ? "spin" : undefined} size={15} />Recheck</button></div>
    <section className="provider-cards">{providerCards.map((provider) => <article key={provider.name}><ModelLogo provider={provider.name} size={42} /><div><h3>{provider.name}</h3><span className="provider-health" data-state={provider.state.toLowerCase()}><i />{provider.state}</span></div><strong>{provider.detail}</strong>{provider.models.length > 0 && <small className="provider-models">{provider.models.join(" · ")}</small>}</article>)}{!loadingProviders && providerCards.length === 0 && <p>{providerError ?? "No routable providers reported."}</p>}</section>
    <section className="panel model-table-panel"><div className="panel-heading"><div><h2>Model policies</h2><p>Project rules are enforced by the chat gateway and every recovery preflight.</p></div><span className="policy-seal"><ShieldCheck size={15} />{loadingPolicies ? "Loading rules" : "Admission active"}</span></div>{error && <div className="error-row">Policy save failed: {error}</div>}<div className="table-scroll"><table className="model-table"><thead><tr><th>Provider</th><th>Model</th><th>Runs</th><th>Tokens</th><th>Per-call limit</th><th>Latency</th><th>Policy mode</th></tr></thead><tbody>{models.map((model) => { const policy = policies[model.key] ?? { mode: "observe" as PolicyMode, tokenLimit: null }; const saving = savingKeys.has(model.key); const limitLabel = policy.tokenLimit !== null ? `${formatTokens(policy.tokenLimit)} max` : policy.mode === "block" ? "Model disabled" : policy.mode === "warn" ? "Warn every call" : "All request sizes"; return <tr key={model.key}><td>{model.provider}</td><td><div className="model-identity"><ModelLogo model={model.model} provider={model.provider} /><div><strong>{model.model}</strong><small>{saving ? "Saving policy" : model.runs ? `${model.active} active / ${model.completed} completed` : "Installed / no runs"}</small></div></div></td><td>{model.runs}</td><td>{formatTokens(model.tokens)}</td><td><label className="token-limit"><input aria-label={`${model.model} per-call token limit`} defaultValue={policy.tokenLimit ?? ""} disabled={saving} key={`${model.key}-${policy.tokenLimit ?? "none"}`} min="1" onBlur={(event) => { const value = event.target.value ? Number(event.target.value) : null; if (value !== policy.tokenLimit) void onLimit(model.provider, model.model, value).catch(() => undefined); }} placeholder="No limit" type="number" /><span>{limitLabel}</span></label></td><td>{model.averageLatencyMs === null ? "No sample" : formatDuration(model.averageLatencyMs)}</td><td><div className="policy-control" role="group" aria-label={`${model.model} policy mode`}>{(["observe", "warn", "block"] as PolicyMode[]).map((mode) => <button data-active={policy.mode === mode} disabled={saving} key={mode} onClick={() => void onMode(model.provider, model.model, mode).catch(() => undefined)} type="button">{mode}</button>)}</div></td></tr>; })}</tbody></table></div></section>
  </div>;
}
