import { Building2, KeyRound, LogOut, ShieldCheck } from "lucide-react";

import type { ConnectionConfig, DataMode, WorkspaceContext } from "@/lib/types";

export function ProfileView({ workspace, mode, connection, onDisconnect }: { workspace: WorkspaceContext; mode: DataMode; connection: ConnectionConfig | null; onDisconnect: () => void }) {
  return <div className="module-view profile-view view-enter"><div className="page-intro"><div><h2>Profile</h2><p>Identity, workspace access, and current browser session.</p></div></div>
    <section className="profile-header panel"><span className="profile-avatar">API</span><div><h3>{workspace.projectName}</h3><p>Project-scoped session</p><span className="access-badge"><ShieldCheck size={14} />Authenticated scope</span></div></section>
    <div className="profile-grid"><section className="panel profile-section"><div className="settings-title"><KeyRound size={19} /><div><h3>Authentication</h3><p>Current access method</p></div></div><dl className="setting-rows"><div><dt>Session</dt><dd>{mode === "live" ? "Project API key" : "Disconnected"}</dd></div><div><dt>Credential storage</dt><dd>{connection ? "Memory only" : "None"}</dd></div><div><dt>Scope</dt><dd>{workspace.projectSlug || "Not connected"}</dd></div></dl></section>
      <section className="panel profile-section"><div className="settings-title"><Building2 size={19} /><div><h3>Workspace access</h3><p>Current project scope</p></div></div><dl className="setting-rows"><div><dt>Organization</dt><dd>{workspace.organizationName}</dd></div><div><dt>Project</dt><dd>{workspace.projectName}</dd></div><div><dt>Applications</dt><dd>{workspace.applications.length}</dd></div></dl></section>
      <section className="panel profile-section wide"><div className="settings-title"><KeyRound size={19} /><div><h3>Session security</h3><p>The project key is never written to browser storage.</p></div></div><div className="session-row"><div><span>Control API</span><code>{connection?.apiUrl ?? "Not connected"}</code></div><div><span>Credential</span><strong>{connection ? "Memory only" : "None"}</strong></div>{connection && <button className="secondary-button danger-button" onClick={onDisconnect} type="button"><LogOut size={15} />End session</button>}</div></section></div>
  </div>;
}
