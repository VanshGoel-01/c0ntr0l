import type {
  BudgetPolicy,
  ConnectionConfig,
  Execution,
  ExecutionDetail,
  ExecutionSpan,
  Health,
  Incident,
  IncidentStatus,
  RuntimeCancellationResult,
  RuntimeCheckpoint,
  RuntimeIntervention,
  RuntimeRecoveryRequest,
  RuntimeRecoveryResult,
  RunStatus,
  UsageRecord,
  WorkspaceContext,
} from "@/lib/types";

type ApiExecution = {
  id: string;
  request_id: string | null;
  project_id: string | null;
  project_name: string | null;
  application_id: string | null;
  application_name: string | null;
  agent_name: string | null;
  status: string;
  requested_model: string;
  active_provider: string | null;
  active_model: string | null;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  span_count: number;
  total_tokens: number;
  total_cost: string | number;
  final_reason: string | null;
  error_code: string | null;
  metadata?: Record<string, unknown>;
};

type ApiSpan = {
  id: string;
  parent_span_id: string | null;
  sequence_no: number;
  kind: string;
  name: string;
  tool_name: string | null;
  status: string;
  duration_ms: number | null;
  error_code: string | null;
  started_at: string;
  completed_at: string | null;
  attributes?: Record<string, unknown>;
};

type ApiUsage = {
  source_type: string;
  provider: string | null;
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_amount: string | number;
  currency: string;
  latency_ms: number | null;
  observed_at: string;
};

type ApiExecutionDetail = ApiExecution & { spans: ApiSpan[]; usage: ApiUsage[] };
type ApiCheckpoint = {
  id: string;
  execution_id: string;
  status: string;
  content_fingerprint: string;
  packet: {
    version: string;
    task: string;
    source_execution_id: string;
    source_provider: string;
    source_model: string;
    completed_work: string[];
    failed_operation: Record<string, unknown>;
    reason_for_intervention: string;
    recommended_action: string;
    evidence: Record<string, unknown>;
    created_at: string;
  };
  created_at: string;
  consumed_at: string | null;
};
type ApiIntervention = {
  execution_id: string;
  execution_status: string;
  policy_code: string;
  policy_mode: "observe" | "warn" | "enforce";
  outcome: string;
  reason: string;
  evidence: Record<string, unknown>;
  decided_at: string;
  checkpoint: ApiCheckpoint | null;
};
type ApiRecoveryResult = {
  source_execution_id: string;
  strategy: RuntimeRecoveryResult["strategy"];
  status: string;
  resumed_execution_id: string | null;
  target_provider: string | null;
  target_model: string | null;
  completion: {
    id: string;
    choices: Array<{ message: { content: string | null } }>;
    usage: { total_tokens: number };
  } | null;
  checkpoint: ApiCheckpoint;
  message: string;
};
type ApiCancellationResult = { execution_id: string; status: string; checkpoint_id: string | null };
type ApiIncident = {
  id: string;
  execution_id: string;
  trace_id: string;
  application_name: string;
  provider: string;
  model: string;
  incident_type: Incident["type"];
  severity: Incident["severity"];
  status: IncidentStatus;
  title: string;
  evidence: Record<string, unknown>;
  created_at: string;
};
type ApiBudget = {
  id: string;
  name: string;
  scope_type: string;
  scope_id: string;
  period_type: string;
  mode: "observe" | "warn" | "enforce";
  max_requests: number | null;
  max_tokens: number | null;
  max_cost: string | number | null;
  currency: string;
  is_enabled: boolean;
};
type ApiWorkspace = {
  organization_id: string;
  organization_name: string;
  project_id: string;
  project_slug: string;
  project_name: string;
  applications: Array<{ id: string; slug: string; name: string; environment: string; status: string }>;
  budgets: ApiBudget[];
  requests_24h: number;
  tokens_24h: number;
  cost_24h: string | number;
};

function normalizeUrl(url: string): string {
  const parsed = new URL(url.trim());
  const isLocal = parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1" || parsed.hostname === "::1";
  if (parsed.protocol !== "https:" && !(parsed.protocol === "http:" && isLocal)) {
    throw new Error("Use HTTPS for remote APIs. HTTP is allowed only for localhost.");
  }
  parsed.username = "";
  parsed.password = "";
  parsed.hash = "";
  return parsed.toString().replace(/\/+$/, "");
}

export function normalizeConnection(config: ConnectionConfig): ConnectionConfig {
  const apiKey = config.apiKey.trim();
  if (!apiKey.startsWith("ctl_") || apiKey.length < 36 || apiKey.length > 64) {
    throw new Error("Enter a valid c0ntr0l project API key.");
  }
  return { apiUrl: normalizeUrl(config.apiUrl), apiKey };
}

function mapStatus(status: string): RunStatus {
  const known: RunStatus[] = ["accepted", "running", "completed", "failed", "blocked", "cancelled", "handed_off"];
  return known.includes(status as RunStatus) ? status as RunStatus : "failed";
}

function mapExecution(value: ApiExecution): Execution {
  return {
    id: value.id,
    traceId: value.request_id ?? value.id,
    projectId: value.project_id,
    project: value.project_name ?? "Unassigned",
    applicationId: value.application_id,
    application: value.application_name ?? "Unassigned",
    agent: value.agent_name,
    status: mapStatus(value.status),
    model: value.active_model ?? value.requested_model,
    provider: value.active_provider ?? "Unassigned",
    startedAt: value.started_at,
    completedAt: value.completed_at,
    durationMs: value.duration_ms,
    totalTokens: value.total_tokens,
    totalCost: Number(value.total_cost),
    spanCount: value.span_count,
    errorCode: value.error_code ?? undefined,
    finalReason: value.final_reason ?? undefined,
    metadata: value.metadata ?? {},
  };
}

function mapSpan(value: ApiSpan): ExecutionSpan {
  return {
    id: value.id,
    parentSpanId: value.parent_span_id,
    sequenceNo: value.sequence_no,
    kind: value.kind,
    name: value.name,
    toolName: value.tool_name,
    status: value.status,
    durationMs: value.duration_ms,
    errorCode: value.error_code,
    startedAt: value.started_at,
    completedAt: value.completed_at,
    attributes: value.attributes ?? {},
  };
}

function mapUsage(value: ApiUsage): UsageRecord {
  return {
    sourceType: value.source_type,
    provider: value.provider,
    model: value.model,
    inputTokens: value.input_tokens,
    outputTokens: value.output_tokens,
    totalTokens: value.total_tokens,
    costAmount: Number(value.cost_amount),
    currency: value.currency,
    latencyMs: value.latency_ms,
    observedAt: value.observed_at,
  };
}

function mapBudget(value: ApiBudget): BudgetPolicy {
  return {
    id: value.id,
    name: value.name,
    scopeType: value.scope_type,
    scopeId: value.scope_id,
    periodType: value.period_type,
    mode: value.mode,
    maxRequests: value.max_requests,
    maxTokens: value.max_tokens,
    maxCost: value.max_cost === null ? null : Number(value.max_cost),
    currency: value.currency,
    isEnabled: value.is_enabled,
  };
}

function mapCheckpoint(value: ApiCheckpoint): RuntimeCheckpoint {
  return {
    id: value.id,
    executionId: value.execution_id,
    status: value.status,
    contentFingerprint: value.content_fingerprint,
    packet: {
      version: value.packet.version,
      task: value.packet.task,
      sourceExecutionId: value.packet.source_execution_id,
      sourceProvider: value.packet.source_provider,
      sourceModel: value.packet.source_model,
      completedWork: value.packet.completed_work,
      failedOperation: value.packet.failed_operation,
      reasonForIntervention: value.packet.reason_for_intervention,
      recommendedAction: value.packet.recommended_action,
      evidence: value.packet.evidence,
      createdAt: value.packet.created_at,
    },
    createdAt: value.created_at,
    consumedAt: value.consumed_at,
  };
}

function mapIntervention(value: ApiIntervention): RuntimeIntervention {
  return {
    executionId: value.execution_id,
    executionStatus: value.execution_status,
    policyCode: value.policy_code,
    policyMode: value.policy_mode,
    outcome: value.outcome,
    reason: value.reason,
    evidence: value.evidence,
    decidedAt: value.decided_at,
    checkpoint: value.checkpoint ? mapCheckpoint(value.checkpoint) : null,
  };
}

function evidenceLines(evidence: Record<string, unknown>): string[] {
  return Object.entries(evidence).slice(0, 8).map(([key, value]) => {
    const rendered = typeof value === "object" ? JSON.stringify(value) : String(value);
    return `${key.replaceAll("_", " ")}: ${rendered}`;
  });
}

function mapIncident(value: ApiIncident): Incident {
  const reason = typeof value.evidence.reason === "string" ? value.evidence.reason : value.title;
  const copy: Record<ApiIncident["incident_type"], { description: string; impact: string; recommendation: string }> = {
    runaway_loop: {
      description: reason,
      impact: "The circuit breaker prevented another non-progressing operation from consuming resources.",
      recommendation: "Inspect the repeated operation and resume from the saved checkpoint with changed arguments.",
    },
    budget_exceeded: {
      description: reason,
      impact: "The model call was blocked before it could exceed an enforced project budget.",
      recommendation: "Reduce the request size, change the budget policy, or resume through an approved route.",
    },
    provider_failure: {
      description: reason,
      impact: "The application did not receive a usable provider response.",
      recommendation: "Inspect provider health and retry through a configured fallback.",
    },
    handoff_failure: {
      description: reason,
      impact: "The saved checkpoint remains available, but automatic continuation did not complete.",
      recommendation: "Retry with another configured model or resume manually from the checkpoint.",
    },
    manual_intervention: {
      description: reason,
      impact: "Policy intervention stopped the current execution before additional work was performed.",
      recommendation: "Review the policy evidence before resuming or ending the task.",
    },
  };
  const details = copy[value.incident_type] ?? copy.manual_intervention;
  return {
    id: value.id,
    executionId: value.execution_id,
    traceId: value.trace_id,
    application: value.application_name,
    model: value.model,
    type: value.incident_type,
    severity: value.severity,
    status: value.status,
    title: value.title,
    description: details.description,
    impact: details.impact,
    evidence: evidenceLines(value.evidence),
    recommendation: details.recommendation,
    createdAt: value.created_at,
  };
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function authHeaders(config: ConnectionConfig): Record<string, string> {
  return { Authorization: `Bearer ${config.apiKey}` };
}

export async function getHealth(apiUrl: string, signal?: AbortSignal): Promise<Health> {
  return readJson<Health>(await fetch(`${normalizeUrl(apiUrl)}/health`, { cache: "no-store", signal }));
}

export async function listExecutions(config: ConnectionConfig, limit = 100, signal?: AbortSignal): Promise<Execution[]> {
  const response = await fetch(`${normalizeUrl(config.apiUrl)}/api/v1/executions?limit=${limit}`, { cache: "no-store", headers: authHeaders(config), signal });
  return (await readJson<ApiExecution[]>(response)).map(mapExecution);
}

export async function getExecution(config: ConnectionConfig, executionId: string, signal?: AbortSignal): Promise<ExecutionDetail> {
  const response = await fetch(`${normalizeUrl(config.apiUrl)}/api/v1/executions/${encodeURIComponent(executionId)}`, { cache: "no-store", headers: authHeaders(config), signal });
  const value = await readJson<ApiExecutionDetail>(response);
  return { ...mapExecution(value), spans: value.spans.map(mapSpan), usage: value.usage.map(mapUsage) };
}

export async function getWorkspace(config: ConnectionConfig, signal?: AbortSignal): Promise<WorkspaceContext> {
  const response = await fetch(`${normalizeUrl(config.apiUrl)}/api/v1/workspace`, { cache: "no-store", headers: authHeaders(config), signal });
  const value = await readJson<ApiWorkspace>(response);
  return {
    organizationId: value.organization_id,
    organizationName: value.organization_name,
    projectId: value.project_id,
    projectSlug: value.project_slug,
    projectName: value.project_name,
    applications: value.applications,
    budgets: value.budgets.map(mapBudget),
    requests24h: value.requests_24h,
    tokens24h: value.tokens_24h,
    cost24h: Number(value.cost_24h),
  };
}

export async function listIncidents(config: ConnectionConfig, limit = 100, signal?: AbortSignal): Promise<Incident[]> {
  const response = await fetch(`${normalizeUrl(config.apiUrl)}/api/v1/incidents?limit=${limit}`, { cache: "no-store", headers: authHeaders(config), signal });
  return (await readJson<ApiIncident[]>(response)).map(mapIncident);
}

export async function updateIncidentStatus(config: ConnectionConfig, incidentId: string, status: IncidentStatus): Promise<Incident> {
  const response = await fetch(`${normalizeUrl(config.apiUrl)}/api/v1/incidents/${encodeURIComponent(incidentId)}`, {
    method: "PATCH",
    headers: { ...authHeaders(config), "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  return mapIncident(await readJson<ApiIncident>(response));
}

export async function getRuntimeIntervention(config: ConnectionConfig, executionId: string): Promise<RuntimeIntervention | null> {
  const response = await fetch(`${normalizeUrl(config.apiUrl)}/api/v1/runtime/executions/${encodeURIComponent(executionId)}/intervention`, { cache: "no-store", headers: authHeaders(config) });
  if (response.status === 404) return null;
  return mapIntervention(await readJson<ApiIntervention>(response));
}

export async function recoverRuntimeExecution(config: ConnectionConfig, executionId: string, request: RuntimeRecoveryRequest): Promise<RuntimeRecoveryResult> {
  const response = await fetch(`${normalizeUrl(config.apiUrl)}/api/v1/runtime/executions/${encodeURIComponent(executionId)}/recover`, {
    method: "POST",
    headers: { ...authHeaders(config), "Content-Type": "application/json" },
    body: JSON.stringify({
      strategy: request.strategy,
      target_provider: request.targetProvider,
      target_model: request.targetModel,
      modified_arguments: request.modifiedArguments,
    }),
  });
  const value = await readJson<ApiRecoveryResult>(response);
  return {
    sourceExecutionId: value.source_execution_id,
    strategy: value.strategy,
    status: value.status,
    resumedExecutionId: value.resumed_execution_id,
    targetProvider: value.target_provider,
    targetModel: value.target_model,
    completion: value.completion ? {
      id: value.completion.id,
      content: value.completion.choices[0]?.message.content ?? null,
      totalTokens: value.completion.usage.total_tokens,
    } : null,
    checkpoint: mapCheckpoint(value.checkpoint),
    message: value.message,
  };
}

export async function cancelRuntimeExecution(config: ConnectionConfig, executionId: string): Promise<RuntimeCancellationResult> {
  const response = await fetch(`${normalizeUrl(config.apiUrl)}/api/v1/runtime/executions/${encodeURIComponent(executionId)}/cancel`, {
    method: "POST",
    headers: authHeaders(config),
  });
  const value = await readJson<ApiCancellationResult>(response);
  return { executionId: value.execution_id, status: value.status, checkpointId: value.checkpoint_id };
}
