import { CircleDollarSign, FileWarning, Gauge, ShieldCheck } from "lucide-react";

import { ModelLogo } from "@/components/model-logo";
import { deriveModelStats, formatTokens } from "@/lib/metrics";
import type { Execution, ModelPolicy, WorkspaceContext } from "@/lib/types";

function percent(value: number, limit: number | null): number | null {
  return limit ? Math.min(100, value / limit * 100) : null;
}

export function BudgetsView({ executions, workspace, modelPolicies }: { executions: Execution[]; workspace: WorkspaceContext; modelPolicies: Record<string, ModelPolicy> }) {
  const requests = workspace.requests24h;
  const tokens = workspace.tokens24h;
  const cost = workspace.cost24h;
  const primary = workspace.budgets.find((budget) => budget.isEnabled);
  const requestPercent = percent(requests, primary?.maxRequests ?? null);
  const tokenPercent = percent(tokens, primary?.maxTokens ?? null);
  const models = deriveModelStats(executions);

  return <div className="module-view view-enter"><div className="page-intro"><div><h2>Budgets</h2><p>Observed usage compared with workspace budgets and model-level call limits.</p></div><span className="policy-seal"><ShieldCheck size={16} />Server enforced</span></div>
    <section className="metric-strip budget-metrics">
      <article><span className="metric-icon indigo"><Gauge size={18} /></span><div><span>Requests</span><strong>{requests.toLocaleString()}</strong><small>{primary?.maxRequests ? `${Math.max(0, primary.maxRequests - requests).toLocaleString()} left` : "No request limit"}</small></div></article>
      <article><span className="metric-icon blue"><FileWarning size={18} /></span><div><span>Tokens</span><strong>{formatTokens(tokens)}</strong><small>{primary?.maxTokens ? `${formatTokens(Math.max(0, primary.maxTokens - tokens))} left` : "No token limit"}</small></div></article>
      <article><span className="metric-icon cream"><CircleDollarSign size={18} /></span><div><span>Provider spend</span><strong>${cost.toFixed(2)}</strong><small>Recorded usage ledger</small></div></article>
      <article><span className="metric-icon magenta"><ShieldCheck size={18} /></span><div><span>Policies</span><strong>{workspace.budgets.filter((budget) => budget.isEnabled).length}</strong><small>{workspace.budgets.filter((budget) => budget.mode === "enforce").length} enforced</small></div></article>
    </section>
    <section className="panel utilization-panel"><div className="panel-heading"><div><h2>Budget utilization</h2><p>Current 24-hour usage</p></div></div>{primary ? <div className="utilization-grid"><article><div><span>Request limit</span><strong>{requestPercent?.toFixed(1) ?? "--"}%</strong></div><progress max="100" value={requestPercent ?? 0} /><p>{requests.toLocaleString()} used / {primary.maxRequests?.toLocaleString() ?? "Unlimited"}</p></article><article><div><span>Token limit</span><strong>{tokenPercent?.toFixed(1) ?? "--"}%</strong></div><progress max="100" value={tokenPercent ?? 0} /><p>{tokens.toLocaleString()} used / {primary.maxTokens?.toLocaleString() ?? "Unlimited"}</p></article><article><div><span>Cost limit</span><strong>{primary.maxCost === null ? "Blocked" : `${percent(cost, primary.maxCost)?.toFixed(1)}%`}</strong></div><progress max="100" value={primary.maxCost ? percent(cost, primary.maxCost) ?? 0 : 0} /><p>{primary.maxCost === null ? "No cost allowance configured" : `$${cost.toFixed(2)} used / $${primary.maxCost.toFixed(2)}`}</p></article></div> : <div className="empty-state"><strong>No workspace policy</strong><span>Seed or configure a PostgreSQL budget policy to calculate utilization.</span></div>}</section>
    <section className="panel policy-table-panel"><div className="panel-heading"><div><h2>Workspace policies</h2><p>Read from control.budget_policies</p></div></div><div className="table-scroll"><table><thead><tr><th>Policy</th><th>Scope</th><th>Period</th><th>Mode</th><th>Requests</th><th>Tokens</th><th>Cost</th><th>Status</th></tr></thead><tbody>{workspace.budgets.map((budget) => <tr key={budget.id}><td><strong>{budget.name}</strong></td><td>{budget.scopeType}</td><td>{budget.periodType}</td><td><span className="mode-pill" data-mode={budget.mode}>{budget.mode}</span></td><td>{budget.maxRequests?.toLocaleString() ?? "--"}</td><td>{budget.maxTokens?.toLocaleString() ?? "--"}</td><td>{budget.maxCost === null ? "Blocked" : `$${budget.maxCost.toFixed(2)}`}</td><td>{budget.isEnabled ? "Enabled" : "Paused"}</td></tr>)}</tbody></table></div></section>
    <section className="panel model-budget-panel"><div className="panel-heading"><div><h2>Model call limits</h2><p>Largest observed call compared with each preflight rule</p></div></div><div className="model-budget-list">{models.map((model) => { const policy = modelPolicies[model.key]; const largestCall = Math.max(0, ...executions.filter((run) => run.provider === model.provider && run.model === model.model).map((run) => run.totalTokens)); const used = percent(largestCall, policy?.tokenLimit ?? null); return <article key={model.key}><div className="model-budget-identity"><ModelLogo model={model.model} provider={model.provider} /><div><strong>{model.model}</strong><span>{model.provider}</span></div></div><div><b>{formatTokens(largestCall)}</b><span>{policy?.tokenLimit ? `${formatTokens(policy.tokenLimit)} max` : "No limit"}</span></div><progress max="100" value={used ?? 0} /><span className="mode-pill" data-mode={policy?.mode ?? "observe"}>{policy?.mode ?? "observe"}</span></article>; })}</div></section>
  </div>;
}
