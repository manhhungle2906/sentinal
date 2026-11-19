import { useCallback, useEffect, useState } from "react";
import * as api from "../api/endpoints";
import type { Member } from "../api/types";
import { useAuth } from "../state/auth-context";
import { EmptyState, ErrorState, LoadingState, Spinner } from "../components/States";

export function TeamPage() {
  const { activeWorkspaceId, workspaces } = useAuth();
  const [members, setMembers] = useState<Member[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"analyst" | "viewer">("analyst");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionOk, setActionOk] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const activeWorkspace = workspaces.find((workspace) => workspace.id === activeWorkspaceId);
  const isOwner = activeWorkspace?.role === "owner";

  const load = useCallback(async () => {
    if (!activeWorkspaceId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      setMembers(await api.listMembers(activeWorkspaceId));
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load the members.");
    } finally {
      setLoading(false);
    }
  }, [activeWorkspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!activeWorkspaceId) {
    return (
      <EmptyState
        title="No workspace selected"
        description="Select a workspace to manage its members."
      />
    );
  }

  return (
    <section className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Team</h1>
        <p className="text-sm text-slate-400">
          Owners manage members and sources. Analysts can investigate. Viewers can
          only read.
        </p>
      </div>

      {isOwner ? (
        <form
          className="panel flex flex-wrap items-end gap-3 p-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (!activeWorkspaceId || email.trim() === "") return;
            setBusy(true);
            setActionError(null);
            setActionOk(null);
            void api
              .addMember(activeWorkspaceId, { email: email.trim(), role })
              .then(() => {
                setActionOk(`${email.trim()} was added as ${role}.`);
                setEmail("");
                return load();
              })
              .catch((caught: unknown) =>
                setActionError(
                  caught instanceof Error ? caught.message : "Could not add the member.",
                ),
              )
              .finally(() => setBusy(false));
          }}
        >
          <div className="flex-1 min-w-56">
            <label className="label" htmlFor="member-email">
              Existing account email
            </label>
            <input
              id="member-email"
              type="email"
              className="input"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="analyst@example.com"
              required
            />
          </div>
          <div>
            <label className="label" htmlFor="member-role">
              Role
            </label>
            <select
              id="member-role"
              className="input w-auto"
              value={role}
              onChange={(event) => setRole(event.target.value as "analyst" | "viewer")}
            >
              <option value="analyst">Analyst</option>
              <option value="viewer">Viewer</option>
            </select>
          </div>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? <Spinner /> : null} Add member
          </button>
          {actionOk ? <p className="w-full text-sm text-emerald-300">{actionOk}</p> : null}
          {actionError ? (
            <p role="alert" className="w-full text-sm text-rose-300">
              {actionError}
            </p>
          ) : null}
        </form>
      ) : (
        <p className="panel p-4 text-sm text-slate-400">
          Only the workspace owner can add or remove members.
        </p>
      )}

      {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}

      {loading && members.length === 0 ? (
        <LoadingState label="Loading members…" />
      ) : (
        <div className="panel overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Email</th>
                <th scope="col">Role</th>
                <th scope="col">Joined</th>
              </tr>
            </thead>
            <tbody>
              {members.map((member) => (
                <tr key={member.user_id}>
                  <td>{member.display_name}</td>
                  <td>{member.email}</td>
                  <td>
                    <span className="badge badge-neutral">{member.role}</span>
                  </td>
                  <td>{new Date(member.joined_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
