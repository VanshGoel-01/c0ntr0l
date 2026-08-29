"use client";

import { useCallback, useEffect, useState } from "react";

import type { ConnectionConfig } from "@/lib/types";

export type RuntimeStatus = {
  checkedAt: string;
  ollama: { status: "connected" | "unavailable"; models: string[]; detail?: string };
  mock: { status: "connected" | "unavailable" };
  gemini: { status: "configured" | "not_configured" };
};

export function useProviderStatus(connection: ConnectionConfig | null) {
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const refresh = useCallback(async () => {
    if (!connection) {
      setStatus(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const response = await fetch("/api/runtime-status", {
        cache: "no-store",
        headers: { Authorization: `Bearer ${connection.apiKey}` },
      });
      if (!response.ok) throw new Error("Runtime status unavailable");
      setStatus(await response.json() as RuntimeStatus);
    } catch {
      setStatus(null);
    } finally { setLoading(false); }
  }, [connection]);
  useEffect(() => { void refresh().catch(() => undefined); }, [refresh]);
  return { status, loading, refresh };
}
