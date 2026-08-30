"use client";

import { useCallback, useEffect, useState } from "react";

import { listProviders } from "@/lib/api";
import type { ConnectionConfig, ProviderCatalog } from "@/lib/types";

export function useProviderStatus(connection: ConnectionConfig | null) {
  const [status, setStatus] = useState<ProviderCatalog | null>(null);
  const [loading, setLoading] = useState(false);
  const refresh = useCallback(async () => {
    if (!connection) {
      setStatus(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      setStatus(await listProviders(connection));
    } catch {
      setStatus(null);
    } finally { setLoading(false); }
  }, [connection]);
  useEffect(() => { void refresh().catch(() => undefined); }, [refresh]);
  return { status, loading, refresh };
}
