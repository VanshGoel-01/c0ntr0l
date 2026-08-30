import { ArrowUpRight } from "lucide-react";

import { ModelLogo } from "@/components/model-logo";
import { deriveRisk, formatDuration, relativeTime } from "@/lib/metrics";
import type { ConsoleSettings, Execution } from "@/lib/types";

type ExecutionTableProps = {
  executions: Execution[];
  settings: ConsoleSettings;
  onOpen: (run: Execution) => void;
  emptyMessage?: string;
};

export function ExecutionTable({ executions, settings, onOpen, emptyMessage = "No executions match this view." }: ExecutionTableProps) {
  return <div className="table-scroll">
    <table className="execution-table">
      <thead><tr><th>Status</th><th>Trace ID</th><th>Project</th><th>Application</th><th>Model</th><th>Cost</th><th>Tokens</th><th>Duration</th><th>Risk</th><th>Started</th><th /></tr></thead>
      <tbody>{executions.map((run) => {
        const risk = deriveRisk(run, settings);
        return <tr key={run.id}>
          <td><span className="status-pill" data-status={run.status}>{run.status.replace("_", " ")}</span></td>
          <td><button className="trace-link" onClick={() => onOpen(run)} type="button">{run.traceId}</button></td>
          <td>{run.project}</td><td><strong>{run.application}</strong><small>{run.agent ?? "No agent"}</small></td>
          <td><div className="model-identity"><ModelLogo model={run.model} provider={run.provider} /><div><strong>{run.model}</strong><small>{run.provider}</small></div></div></td><td>${run.totalCost.toFixed(4)}</td><td>{run.totalTokens.toLocaleString()}</td>
          <td>{formatDuration(run.durationMs)}</td><td><span className="risk-pill" data-risk={risk.level}>{risk.reason}</span></td><td>{relativeTime(run.startedAt)}</td>
          <td><button className="row-button" onClick={() => onOpen(run)} title={`Open trace ${run.traceId}`} type="button"><ArrowUpRight size={15} /></button></td>
        </tr>;
      })}</tbody>
    </table>
    {executions.length === 0 && <div className="empty-table">{emptyMessage}</div>}
  </div>;
}
