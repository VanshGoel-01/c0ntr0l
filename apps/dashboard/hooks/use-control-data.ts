"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { cancelRuntimeExecution, getExecution, getHealth, getRuntimeIntervention, getWorkspace, listExecutions, listIncidents, normalizeConnection, recoverRuntimeExecution, updateIncidentStatus as persistIncidentStatus } from "@/lib/api";
import type { ConnectionConfig, DataMode, Execution, ExecutionDetail, Health, Incident, IncidentStatus, RuntimeIntervention, RuntimeRecoveryRequest, RuntimeRecoveryResult, WorkspaceContext } from "@/lib/types";

const REFRESH_MS = 15_000;
const emptyWorkspace: WorkspaceContext = {
  organizationId: "",
  organizationName: "No workspace",
  projectId: "",
  projectSlug: "",
  projectName: "Not connected",
  applications: [],
  budgets: [],
  requests24h: 0,
  tokens24h: 0,
  cost24h: 0,
};

export function useControlData() {
  const [mode, setMode] = useState<DataMode>("disconnected");
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [workspace, setWorkspace] = useState<WorkspaceContext>(emptyWorkspace);
  const [health, setHealth] = useState<Health | null>(null);
  const [connection, setConnection] = useState<ConnectionConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeRequest = useRef<AbortController | null>(null);

  const refreshTarget = useCallback(async (target: ConnectionConfig) => {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setLoading(true);
    try {
      const [nextHealth, nextExecutions, nextWorkspace, nextIncidents] = await Promise.all([
        getHealth(target.apiUrl, controller.signal),
        listExecutions(target, 100, controller.signal),
        getWorkspace(target, controller.signal),
        listIncidents(target, 100, controller.signal),
      ]);
      setHealth(nextHealth);
      setExecutions(nextExecutions);
      setWorkspace(nextWorkspace);
      setIncidents(nextIncidents);
      setMode("live");
      setError(null);
    } catch (caught) {
      if ((caught as Error).name !== "AbortError") setError((caught as Error).message);
      throw caught;
    } finally {
      if (activeRequest.current === controller) setLoading(false);
    }
  }, []);

  const connect = useCallback(async (next: ConnectionConfig) => {
    const normalized = normalizeConnection(next);
    await refreshTarget(normalized);
    setConnection(normalized);
  }, [refreshTarget]);

  const disconnect = useCallback(() => {
    activeRequest.current?.abort();
    setConnection(null);
    setHealth(null);
    setMode("disconnected");
    setExecutions([]);
    setIncidents([]);
    setWorkspace(emptyWorkspace);
    setError(null);
  }, []);

  const loadExecution = useCallback(async (executionId: string): Promise<ExecutionDetail | null> => {
    if (!connection) return null;
    return getExecution(connection, executionId);
  }, [connection]);

  const loadIntervention = useCallback(async (executionId: string): Promise<RuntimeIntervention | null> => {
    if (!connection) return null;
    return getRuntimeIntervention(connection, executionId);
  }, [connection]);

  const recoverExecution = useCallback(async (executionId: string, request: RuntimeRecoveryRequest): Promise<RuntimeRecoveryResult> => {
    if (!connection) throw new Error("Connect to the live control API before recovering an execution.");
    const result = await recoverRuntimeExecution(connection, executionId, request);
    await refreshTarget(connection);
    return result;
  }, [connection, refreshTarget]);

  const cancelExecution = useCallback(async (executionId: string) => {
    if (!connection) throw new Error("Connect to the live control API before cancelling an execution.");
    const result = await cancelRuntimeExecution(connection, executionId);
    await refreshTarget(connection);
    return result;
  }, [connection, refreshTarget]);

  const updateIncidentStatus = useCallback(async (incidentId: string, status: IncidentStatus) => {
    if (!connection) throw new Error("Connect to the live control API before updating an incident.");
    const updated = await persistIncidentStatus(connection, incidentId, status);
    setIncidents((current) => current.map((incident) => incident.id === updated.id ? updated : incident));
    return updated;
  }, [connection]);

  useEffect(() => {
    if (!connection) return;
    const timer = window.setInterval(() => void refreshTarget(connection).catch(() => undefined), REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [connection, refreshTarget]);

  useEffect(() => () => activeRequest.current?.abort(), []);

  const refresh = useCallback(async () => {
    if (connection) await refreshTarget(connection);
  }, [connection, refreshTarget]);

  return { mode, executions, incidents, workspace, health, connection, loading, error, connect, disconnect, refresh, loadExecution, loadIntervention, recoverExecution, cancelExecution, updateIncidentStatus };
}
