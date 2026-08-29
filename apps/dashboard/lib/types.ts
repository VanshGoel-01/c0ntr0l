import type { LucideIcon } from "lucide-react";

export type ViewId =
  | "overview"
  | "runs"
  | "budgets"
  | "incidents"
  | "models"
  | "settings"
  | "profile";

export type NavigationItem = { id: ViewId; label: string; icon: LucideIcon };
export type RunStatus = "accepted" | "running" | "completed" | "failed" | "blocked" | "cancelled" | "handed_off";
export type RiskLevel = "low" | "medium" | "high" | "critical";
export type PolicyMode = "observe" | "warn" | "block";
export type DataMode = "disconnected" | "live";

export type Execution = {
  id: string;
  traceId: string;
  projectId: string | null;
  project: string;
  applicationId: string | null;
  application: string;
  agent: string | null;
  status: RunStatus;
  model: string;
  provider: string;
  startedAt: string;
  completedAt: string | null;
  durationMs: number | null;
  totalTokens: number;
  totalCost: number;
  spanCount: number;
  errorCode?: string;
  finalReason?: string;
  metadata: Record<string, unknown>;
};

export type ExecutionSpan = {
  id: string;
  parentSpanId: string | null;
  sequenceNo: number;
  kind: string;
  name: string;
  toolName: string | null;
  status: string;
  durationMs: number | null;
  errorCode: string | null;
  startedAt: string;
  completedAt: string | null;
  attributes: Record<string, unknown>;
};

export type UsageRecord = {
  sourceType: string;
  provider: string | null;
  model: string | null;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  costAmount: number;
  currency: string;
  latencyMs: number | null;
  observedAt: string;
};

export type ExecutionDetail = Execution & { spans: ExecutionSpan[]; usage: UsageRecord[] };
export type RecoveryStrategy = "retry_modified" | "model_handoff" | "manual_resume" | "stop";
export type ContinuityPacket = {
  version: string;
  task: string;
  sourceExecutionId: string;
  sourceProvider: string;
  sourceModel: string;
  completedWork: string[];
  failedOperation: Record<string, unknown>;
  reasonForIntervention: string;
  recommendedAction: string;
  evidence: Record<string, unknown>;
  createdAt: string;
};
export type RuntimeCheckpoint = {
  id: string;
  executionId: string;
  status: string;
  contentFingerprint: string;
  packet: ContinuityPacket;
  createdAt: string;
  consumedAt: string | null;
};
export type RuntimeIntervention = {
  executionId: string;
  executionStatus: string;
  policyCode: string;
  policyMode: "observe" | "warn" | "enforce";
  outcome: string;
  reason: string;
  evidence: Record<string, unknown>;
  decidedAt: string;
  checkpoint: RuntimeCheckpoint | null;
};
export type RuntimeRecoveryRequest = {
  strategy: RecoveryStrategy;
  targetProvider?: string;
  targetModel?: string;
  modifiedArguments?: Record<string, unknown>;
};
export type RuntimeRecoveryResult = {
  sourceExecutionId: string;
  strategy: RecoveryStrategy;
  status: string;
  resumedExecutionId: string | null;
  targetProvider: string | null;
  targetModel: string | null;
  completion: { id: string; content: string | null; totalTokens: number } | null;
  checkpoint: RuntimeCheckpoint;
  message: string;
};
export type RuntimeCancellationResult = { executionId: string; status: string; checkpointId: string | null };
export type ModelTarget = { provider: string; model: string };
export type DependencyHealth = { status: string; detail: string | null };
export type Health = { status: string; service: string; version: string; dependencies: Record<string, DependencyHealth> };

export type ApplicationContext = { id: string; slug: string; name: string; environment: string; status: string };
export type BudgetPolicy = {
  id: string;
  name: string;
  scopeType: string;
  scopeId: string;
  periodType: string;
  mode: "observe" | "warn" | "enforce";
  maxRequests: number | null;
  maxTokens: number | null;
  maxCost: number | null;
  currency: string;
  isEnabled: boolean;
};
export type WorkspaceContext = {
  organizationId: string;
  organizationName: string;
  projectId: string;
  projectSlug: string;
  projectName: string;
  applications: ApplicationContext[];
  budgets: BudgetPolicy[];
  requests24h: number;
  tokens24h: number;
  cost24h: number;
};

export type ConnectionConfig = { apiUrl: string; apiKey: string };
export type IncidentStatus = "open" | "acknowledged" | "resolved";
export type IncidentType = "runaway_loop" | "provider_failure" | "budget_exceeded" | "handoff_failure" | "manual_intervention";
export type Incident = {
  id: string;
  executionId: string;
  traceId: string;
  application: string;
  model: string;
  type: IncidentType;
  severity: "info" | "warning" | "critical";
  status: IncidentStatus;
  title: string;
  description: string;
  impact: string;
  evidence: string[];
  recommendation: string;
  createdAt: string;
};

export type ConsoleSettings = {
  repeatThreshold: number;
  highTokenThreshold: number;
  slowRunThresholdMs: number;
  retentionDays: number;
  notifyCritical: boolean;
  notifyWarnings: boolean;
  storePrompts: boolean;
};
export type ModelPolicy = { mode: PolicyMode; tokenLimit: number | null };
