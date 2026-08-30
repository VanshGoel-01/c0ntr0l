"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { listModelPolicies, upsertModelPolicy } from "@/lib/api";
import type { ConnectionConfig, ModelPolicy, PolicyMode } from "@/lib/types";

function policyKey(provider: string, model: string): string {
  return `${provider}/${model}`;
}

export function useModelPolicies(connection: ConnectionConfig | null) {
  const [policies, setPolicies] = useState<Record<string, ModelPolicy>>({});
  const [loading, setLoading] = useState(false);
  const [savingKeys, setSavingKeys] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(policies);
  const activeConnection = useRef(connection);
  const saveQueue = useRef<Map<string, Promise<unknown>>>(new Map());

  const replacePolicies = useCallback((next: Record<string, ModelPolicy>) => {
    latest.current = next;
    setPolicies(next);
  }, []);

  useEffect(() => {
    activeConnection.current = connection;
    saveQueue.current.clear();
    replacePolicies({});
    setSavingKeys(new Set());
    if (!connection) {
      setLoading(false);
      setError(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void listModelPolicies(connection, controller.signal)
      .then((rows) => replacePolicies(Object.fromEntries(rows.map((row) => [
        policyKey(row.provider, row.model),
        { mode: row.mode, tokenLimit: row.token_limit },
      ]))))
      .catch((caught: Error) => {
        if (caught.name !== "AbortError") setError(caught.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [connection, replacePolicies]);

  const persist = useCallback(async (provider: string, model: string, nextPolicy: ModelPolicy) => {
    if (!connection) throw new Error("Connect to the control API before saving model policies.");
    const targetConnection = connection;
    const key = policyKey(provider, model);
    const previous = latest.current[key];
    const optimistic = { ...nextPolicy };
    replacePolicies({ ...latest.current, [key]: optimistic });
    setSavingKeys((current) => new Set(current).add(key));
    setError(null);
    const previousSave = saveQueue.current.get(key) ?? Promise.resolve();
    const save = previousSave
      .catch(() => undefined)
      .then(() => upsertModelPolicy(targetConnection, provider, model, optimistic));
    saveQueue.current.set(key, save);
    try {
      const saved = await save;
      if (activeConnection.current === targetConnection && latest.current[key] === optimistic) {
        replacePolicies({ ...latest.current, [key]: { mode: saved.mode, tokenLimit: saved.token_limit } });
      }
    } catch (caught) {
      if (activeConnection.current === targetConnection && latest.current[key] === optimistic) {
        const rollback = { ...latest.current };
        if (previous) rollback[key] = previous;
        else delete rollback[key];
        replacePolicies(rollback);
      }
      const message = caught instanceof Error ? caught.message : "Could not save the model policy.";
      if (activeConnection.current === targetConnection) setError(message);
      throw caught;
    } finally {
      if (saveQueue.current.get(key) === save) {
        saveQueue.current.delete(key);
        setSavingKeys((current) => {
          const next = new Set(current);
          next.delete(key);
          return next;
        });
      }
    }
  }, [connection, replacePolicies]);

  const updateMode = useCallback(async (provider: string, model: string, value: PolicyMode) => {
    const current = latest.current[policyKey(provider, model)];
    await persist(provider, model, { mode: value, tokenLimit: current?.tokenLimit ?? null });
  }, [persist]);

  const updateLimit = useCallback(async (provider: string, model: string, value: number | null) => {
    const current = latest.current[policyKey(provider, model)];
    await persist(provider, model, { mode: current?.mode ?? "observe", tokenLimit: value });
  }, [persist]);

  return { policies, updateMode, updateLimit, loading, savingKeys, error };
}
