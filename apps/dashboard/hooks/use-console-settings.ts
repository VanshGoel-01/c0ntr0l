"use client";

import { useEffect, useState } from "react";

import type { ConsoleSettings } from "@/lib/types";

const STORAGE_KEY = "c0ntr0l.console.settings";
export const defaultConsoleSettings: ConsoleSettings = {
  repeatThreshold: 3,
  highTokenThreshold: 12000,
  slowRunThresholdMs: 8000,
  retentionDays: 14,
  notifyCritical: true,
  notifyWarnings: true,
  storePrompts: false,
};

export function useConsoleSettings() {
  const [settings, setSettings] = useState(defaultConsoleSettings);
  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try { setSettings({ ...defaultConsoleSettings, ...JSON.parse(saved) as Partial<ConsoleSettings> }); } catch { localStorage.removeItem(STORAGE_KEY); }
    }
  }, []);
  function update(patch: Partial<ConsoleSettings>) {
    setSettings((current) => {
      const next = { ...current, ...patch };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }
  return { settings, update };
}
