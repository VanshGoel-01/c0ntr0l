"use client";

import { useState } from "react";

import type { ActivityChartData } from "@/lib/metrics";
import { formatTokens } from "@/lib/metrics";

type Metric = "tokens" | "runs";

export function UsageChart({ data }: { data: ActivityChartData }) {
  const [metric, setMetric] = useState<Metric>("tokens");
  const width = 760;
  const height = 210;
  const plot = { left: 44, right: 746, top: 18, bottom: 184 };
  const points = data.points.length ? data.points : [{ label: "Now", runs: 0, tokens: 0 }];
  const values = points.map((point) => point[metric]);
  const peakValue = Math.max(0, ...values);
  const scaleMax = Math.max(1, peakValue);
  const total = values.reduce((sum, value) => sum + value, 0);
  const nonEmpty = values.filter((value) => value > 0);
  const average = nonEmpty.length ? total / nonEmpty.length : 0;
  const xFor = (index: number) => plot.left + (index / Math.max(1, points.length - 1)) * (plot.right - plot.left);
  const yFor = (value: number) => plot.bottom - (value / scaleMax) * (plot.bottom - plot.top);
  const line = points.map((point, index) => `${index === 0 ? "M" : "L"}${xFor(index).toFixed(1)},${yFor(point[metric]).toFixed(1)}`).join(" ");
  const area = `${line} L${plot.right},${plot.bottom} L${plot.left},${plot.bottom} Z`;
  const formatValue = (value: number) => metric === "tokens" ? formatTokens(Math.round(value)) : Math.round(value).toLocaleString();

  return <section className="panel activity-panel" aria-labelledby="activity-heading">
    <div className="panel-heading activity-heading"><div><h2 id="activity-heading">Runtime activity</h2><p>{data.windowLabel}</p></div><div className="chart-metric-switch" role="group" aria-label="Activity metric"><button data-active={metric === "tokens"} onClick={() => setMetric("tokens")} type="button">Tokens</button><button data-active={metric === "runs"} onClick={() => setMetric("runs")} type="button">Runs</button></div></div>
    <div className="chart-summary"><div><span>Total {metric}</span><strong>{formatValue(total)}</strong></div><div><span>Average active interval</span><strong>{formatValue(average)}</strong></div><div><span>Peak interval</span><strong>{formatValue(peakValue)}</strong></div></div>
    <div className="activity-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img"><title>{`${metric === "tokens" ? "Token usage" : "Execution count"} over the selected time range`}</title>
        {[0, .5, 1].map((ratio) => <g key={ratio}><line className="grid-line" x1={plot.left} x2={plot.right} y1={yFor(scaleMax * ratio)} y2={yFor(scaleMax * ratio)} /><text className="axis-value" x={plot.left - 9} y={yFor(scaleMax * ratio) + 4} textAnchor="end">{formatValue(peakValue * ratio)}</text></g>)}
        <path className="activity-area" data-metric={metric} d={area} />
        <path className="activity-line" data-metric={metric} d={line} />
        {points.map((point, index) => point[metric] > 0 && <circle className="activity-point" data-metric={metric} key={`${point.label}-${index}`} cx={xFor(index)} cy={yFor(point[metric])} r="4"><title>{`${point.label}: ${formatValue(point[metric])} ${metric}`}</title></circle>)}
      </svg>
      <div className="chart-labels">{points.filter((_, index) => index % 2 === 0 || index === points.length - 1).map((point) => <span key={point.label}>{point.label}</span>)}</div>
    </div>
  </section>;
}
