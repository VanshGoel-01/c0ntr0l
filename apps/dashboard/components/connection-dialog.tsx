"use client";

import { FormEvent, useEffect, useState } from "react";
import { Eye, EyeOff, Link2, LogOut, ShieldCheck, X } from "lucide-react";

import type { ConnectionConfig, DataMode } from "@/lib/types";

type ConnectionDialogProps = {
  open: boolean;
  mode: DataMode;
  connection: ConnectionConfig | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onConnect: (config: ConnectionConfig) => Promise<void>;
  onDisconnect: () => void;
};

export function ConnectionDialog({
  open,
  mode,
  connection,
  loading,
  error,
  onClose,
  onConnect,
  onDisconnect,
}: ConnectionDialogProps) {
  const [apiUrl, setApiUrl] = useState(process.env.NEXT_PUBLIC_CONTROL_API_URL ?? "http://localhost:8000");
  const [apiKey, setApiKey] = useState("");
  const [showKey, setShowKey] = useState(false);

  useEffect(() => {
    if (connection) setApiUrl(connection.apiUrl);
  }, [connection]);

  if (!open) return null;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await onConnect({ apiUrl, apiKey });
      setApiKey("");
      onClose();
    } catch {
      // The shared data hook exposes the request error below the form.
    }
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section aria-labelledby="connection-title" aria-modal="true" className="dialog-panel" role="dialog">
        <div className="dialog-heading">
          <div>
            <span className="eyebrow">Workspace data source</span>
            <h2 id="connection-title">Control plane connection</h2>
          </div>
          <button className="icon-button" onClick={onClose} title="Close connection dialog" type="button"><X size={17} /></button>
        </div>

        {mode === "live" && connection ? (
          <div className="connected-state">
            <span className="connection-seal"><ShieldCheck size={20} /></span>
            <div><strong>Live runtime connected</strong><code>{connection.apiUrl}</code></div>
            <button className="secondary-button danger-button" onClick={() => { onDisconnect(); onClose(); }} type="button">
              <LogOut size={15} /> Disconnect
            </button>
          </div>
        ) : (
          <form className="connection-form" onSubmit={submit}>
            <label>
              <span>API base URL</span>
              <input onChange={(event) => setApiUrl(event.target.value)} required type="url" value={apiUrl} />
            </label>
            <label>
              <span>Project API key</span>
              <div className="secret-input">
                <input
                  autoComplete="off"
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder="ctl_..."
                  required
                  type={showKey ? "text" : "password"}
                  value={apiKey}
                />
                <button onClick={() => setShowKey((value) => !value)} title={showKey ? "Hide API key" : "Show API key"} type="button">
                  {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </label>
            <p className="security-note"><ShieldCheck size={14} /> The key stays in memory only and is discarded on reload or disconnect.</p>
            {error && <p className="form-error">{error}</p>}
            <div className="dialog-actions">
              <button className="secondary-button" onClick={onClose} type="button">Cancel</button>
              <button className="primary-button" disabled={loading} type="submit"><Link2 size={15} />{loading ? "Verifying..." : "Verify and connect"}</button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}
