"use client";

import { useCallback, useEffect, useState } from "react";

import { listProviders } from "@/lib/api";
import type { ConnectionConfig, ProviderCatalog } from "@/lib/types";

export function useProviderStatus(connection: ConnectionConfig | null) {
  const [status, setStatus] = useState<ProviderCatalog | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    if (!connection) {
      setStatus(null);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setStatus(await listProviders(connection));
    } catch (caught) {
      setStatus(null);
      setError(caught instanceof Error ? caught.message : "Could not load providers.");
    } finally { setLoading(false); }
  }, [connection]);
  useEffect(() => { void refresh().catch(() => undefined); }, [refresh]);
  return { status, loading, error, refresh };
}
