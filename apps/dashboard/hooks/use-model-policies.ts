"use client";

import { useEffect, useState } from "react";

import type { ModelPolicy, PolicyMode } from "@/lib/types";

const STORAGE_KEY = "c0ntr0l.model.policies";

export function useModelPolicies() {
  const [policies, setPolicies] = useState<Record<string, ModelPolicy>>({});
  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try { setPolicies((current) => ({ ...current, ...JSON.parse(saved) as Record<string, ModelPolicy> })); } catch { localStorage.removeItem(STORAGE_KEY); }
    }
  }, []);
  function updateMode(key: string, value: PolicyMode) {
    setPolicies((current) => {
      const next = { ...current, [key]: { mode: value, tokenLimit: current[key]?.tokenLimit ?? null } };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }
  function updateLimit(key: string, value: number | null) {
    setPolicies((current) => {
      const next = { ...current, [key]: { mode: current[key]?.mode ?? "observe", tokenLimit: value } };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }
  return { policies, updateMode, updateLimit };
}
