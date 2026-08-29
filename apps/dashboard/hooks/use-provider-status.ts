"use client";

import { useCallback, useEffect, useState } from "react";

export type RuntimeStatus = {
  checkedAt: string;
  ollama: { status: "connected" | "unavailable"; models: string[]; detail?: string };
  mock: { status: "connected" | "unavailable" };
  gemini: { status: "configured" | "not_configured" };
};

export function useProviderStatus() {
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/runtime-status", { cache: "no-store" });
      if (!response.ok) throw new Error("Runtime status unavailable");
      setStatus(await response.json() as RuntimeStatus);
    } catch {
      setStatus(null);
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { void refresh().catch(() => undefined); }, [refresh]);
  return { status, loading, refresh };
}
