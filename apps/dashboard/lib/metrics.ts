import type { ConsoleSettings, Execution, Incident, RiskLevel } from "@/lib/types";

export type RuntimeMetrics = {
  successRate: number;
  completed: number;
  terminal: number;
  active: number;
  tokens: number;
  p95LatencyMs: number | null;
  attention: number;
  failed: number;
  blocked: number;
  totalCost: number;
};

export type ModelStats = {
  key: string;
  provider: string;
  model: string;
  runs: number;
  active: number;
  completed: number;
  tokens: number;
  cost: number;
  averageLatencyMs: number | null;
  lastUsedAt: string;
};

export type ApplicationStats = {
  name: string;
  runs: number;
  active: number;
  tokens: number;
  cost: number;
  incidents: number;
  models: Array<{ name: string; tokens: number }>;
};

export type ActivityChartData = {
  windowLabel: string;
  points: Array<{ label: string; runs: number; tokens: number }>;
};

export function deriveMetrics(executions: Execution[]): RuntimeMetrics {
  const completed = executions.filter((run) => run.status === "completed").length;
  const failed = executions.filter((run) => run.status === "failed").length;
  const blocked = executions.filter((run) => run.status === "blocked" || run.status === "cancelled").length;
  const active = executions.filter((run) => run.status === "running" || run.status === "accepted").length;
  const terminal = completed + failed + blocked;
  const durations = executions.map((run) => run.durationMs).filter((value): value is number => value !== null).sort((a, b) => a - b);
  return {
    successRate: terminal === 0 ? 0 : (completed / terminal) * 100,
    completed,
    terminal,
    active,
    tokens: executions.reduce((sum, run) => sum + run.totalTokens, 0),
    p95LatencyMs: durations.length > 0 ? durations[Math.max(0, Math.ceil(durations.length * 0.95) - 1)] : null,
    attention: failed + blocked,
    failed,
    blocked,
    totalCost: executions.reduce((sum, run) => sum + run.totalCost, 0),
  };
}

export function deriveRisk(run: Execution, settings: ConsoleSettings): { level: RiskLevel; reason: string } {
  const repeatCount = Number(run.metadata.repeat_count ?? 0);
  if (run.status === "blocked" || run.status === "cancelled" || repeatCount > settings.repeatThreshold) {
    return { level: "critical", reason: run.errorCode === "max_tool_repeats" ? "Loop blocked" : "Policy block" };
  }
  if (run.status === "failed") return { level: "high", reason: run.errorCode?.replaceAll("_", " ") ?? "Run failed" };
  if (run.totalTokens >= settings.highTokenThreshold) return { level: "medium", reason: "High tokens" };
  if (run.durationMs !== null && run.durationMs >= settings.slowRunThresholdMs) return { level: "medium", reason: "Slow run" };
  if (run.status === "running") return { level: "low", reason: "Monitored" };
  return { level: "low", reason: "Clear" };
}

export function deriveModelStats(executions: Execution[]): ModelStats[] {
  const groups = new Map<string, Execution[]>();
  for (const run of executions) {
    const key = `${run.provider}/${run.model}`;
    groups.set(key, [...(groups.get(key) ?? []), run]);
  }
  return [...groups.entries()].map(([key, runs]) => {
    const durations = runs.map((run) => run.durationMs).filter((value): value is number => value !== null);
    return {
      key, provider: runs[0].provider, model: runs[0].model, runs: runs.length,
      active: runs.filter((run) => run.status === "running" || run.status === "accepted").length,
      completed: runs.filter((run) => run.status === "completed").length,
      tokens: runs.reduce((sum, run) => sum + run.totalTokens, 0),
      cost: runs.reduce((sum, run) => sum + run.totalCost, 0),
      averageLatencyMs: durations.length ? Math.round(durations.reduce((sum, value) => sum + value, 0) / durations.length) : null,
      lastUsedAt: runs.map((run) => run.startedAt).sort().at(-1) ?? runs[0].startedAt,
    };
  }).sort((a, b) => b.tokens - a.tokens);
}

export function deriveApplicationStats(executions: Execution[], incidents: Incident[]): ApplicationStats[] {
  const groups = new Map<string, Execution[]>();
  for (const run of executions) groups.set(run.application, [...(groups.get(run.application) ?? []), run]);
  return [...groups.entries()].map(([name, runs]) => {
    const modelTokens = new Map<string, number>();
    for (const run of runs) modelTokens.set(run.model, (modelTokens.get(run.model) ?? 0) + run.totalTokens);
    return {
      name, runs: runs.length,
      active: runs.filter((run) => run.status === "running" || run.status === "accepted").length,
      tokens: runs.reduce((sum, run) => sum + run.totalTokens, 0),
      cost: runs.reduce((sum, run) => sum + run.totalCost, 0),
      incidents: incidents.filter((incident) => incident.application === name && incident.status !== "resolved").length,
      models: [...modelTokens.entries()].map(([model, tokens]) => ({ name: model, tokens })).sort((a, b) => b.tokens - a.tokens),
    };
  }).sort((a, b) => b.tokens - a.tokens);
}

export function deriveActivityChart(executions: Execution[], buckets = 12): ActivityChartData {
  if (!executions.length) return { windowLabel: "No activity", points: [] };
  const now = Date.now();
  const oldest = Math.min(...executions.map((run) => new Date(run.startedAt).getTime()));
  const rangeMinutes = Math.max(1, Math.ceil((now - oldest) / 60_000));
  const intervalOptions = [5, 15, 30, 60, 120, 360, 720, 1_440];
  const requiredInterval = rangeMinutes / Math.max(1, buckets - 1);
  const bucketMinutes = intervalOptions.find((minutes) => minutes >= requiredInterval) ?? 1_440;
  const bucketMs = bucketMinutes * 60_000;
  const end = Math.ceil(now / bucketMs) * bucketMs;
  const start = end - bucketMs * (buckets - 1);
  const points = Array.from({ length: buckets }, (_, index) => ({
    label: formatBucketLabel(new Date(start + bucketMs * index), bucketMinutes),
    runs: 0,
    tokens: 0,
  }));
  for (const run of executions) {
    const index = Math.floor((new Date(run.startedAt).getTime() - start) / bucketMs);
    if (index >= 0 && index < buckets) {
      const point = points[index];
      point.runs += 1;
      point.tokens += run.totalTokens;
    }
  }
  return { windowLabel: formatActivityWindow(new Date(start), new Date(end), bucketMinutes), points };
}

function formatBucketLabel(date: Date, bucketMinutes: number): string {
  if (bucketMinutes >= 1_440) return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return date.toLocaleTimeString("en-US", { hour: "numeric", minute: bucketMinutes < 60 ? "2-digit" : undefined });
}

function formatActivityWindow(start: Date, end: Date, bucketMinutes: number): string {
  if (bucketMinutes >= 1_440) {
    return `${start.toLocaleDateString("en-US", { month: "short", day: "numeric" })} - ${end.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
  }
  const date = (value: Date) => value.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  const time = (value: Date) => value.toLocaleTimeString("en-US", { hour: "numeric", minute: bucketMinutes < 60 ? "2-digit" : undefined });
  if (start.toDateString() !== end.toDateString()) return `${date(start)}, ${time(start)} - ${date(end)}, ${time(end)}`;
  return `${date(end)}, ${time(start)} - ${time(end)}`;
}

export function formatDuration(duration: number | null): string {
  if (duration === null) return "Active";
  if (duration < 1000) return `${duration} ms`;
  return `${(duration / 1000).toFixed(2)} s`;
}

export function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(2)}M`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(1)}K`;
  return tokens.toLocaleString();
}

export function relativeTime(timestamp: string): string {
  const delta = Date.now() - new Date(timestamp).getTime();
  if (delta < 60_000) return "Just now";
  const minutes = Math.round(delta / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}
