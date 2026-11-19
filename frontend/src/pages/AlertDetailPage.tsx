import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import * as api from "../api/endpoints";
import type { AlertDetail, AlertStatus, Member } from "../api/types";
import { isTerminal, RULE_DESCRIPTIONS } from "../api/types";
import { useAuth } from "../state/auth-context";
import { SeverityBadge, StatusBadge } from "../components/Badges";
import { EmptyState, ErrorState, LoadingState, Spinner } from "../components/States";

const NEXT_STATUSES: AlertStatus[] = ["investigating", "resolved", "false_positive"];

export function AlertDetailPage() {
  const { alertId } = useParams<{ alertId: string }>();
  const { activeWorkspaceId, user } = useAuth();
  const [alert, setAlert] = useState<AlertDetail | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [comment, setComment] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!activeWorkspaceId || !alertId) {
      setLoading(false);
      return;
    }
    try {
      const result = await api.getAlert(activeWorkspaceId, alertId);
      setAlert(result);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load the alert.");
    } finally {
      setLoading(false);
    }
  }, [activeWorkspaceId, alertId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!activeWorkspaceId) return;
    void api
      .listMembers(activeWorkspaceId)
      .then(setMembers)
      .catch(() => setMembers([]));
  }, [activeWorkspaceId]);

  async function runAction(action: () => Promise<AlertDetail>) {
    setBusy(true);
    setActionError(null);
    try {
      setAlert(await action());
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "The update failed.");
    } finally {
      setBusy(false);
    }
  }

  if (!activeWorkspaceId) {
    return (
      <EmptyState
        title="No workspace selected"
        description="Select a workspace to view this alert."
      />
    );
  }

  if (loading && alert === null) {
    return <LoadingState label="Loading alert…" />;
  }

  if (error || alert === null) {
    return (
      <div className="space-y-4">
        <ErrorState message={error ?? "The alert could not be loaded."} onRetry={() => void load()} />
        <Link className="btn" to="/alerts">
          Back to alerts
        </Link>
      </div>
    );
  }

  const terminal = isTerminal(alert.status);
  const assignableMembers = members.filter(
    (member) => member.role === "owner" || member.role === "analyst",
  );

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link className="text-sm text-sky-300 underline-offset-2 hover:underline" to="/alerts">
            ← Back to alerts
          </Link>
          <h1 className="mt-1 flex flex-wrap items-center gap-2 text-xl font-semibold">
            <span className="font-mono text-base">{alert.rule_key}</span>
            <SeverityBadge severity={alert.severity} />
            <StatusBadge status={alert.status} />
          </h1>
          <p className="text-sm text-slate-400">Source IP {alert.source_ip}</p>
        </div>
        <button type="button" className="btn" onClick={() => void load()}>
          Refresh
        </button>
      </div>

      {actionError ? (
        <p role="alert" className="text-sm text-rose-300">
          {actionError}
        </p>
      ) : null}

      <div className="panel p-4">
        <h2 className="text-sm font-semibold">Why this fired</h2>
        <p className="mt-2 text-sm text-slate-300">
          {RULE_DESCRIPTIONS[alert.rule_key] ?? "This rule has no description."}
        </p>
        <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Fact label="Rule condition" value={alert.rule_key} />
          <Fact label="Actual count" value={String(alert.count_at_trigger)} />
          <Fact label="Threshold" value={String(alert.threshold)} />
          <Fact label="Window" value={`${alert.window_seconds} seconds`} />
          <Fact label="Interval start" value={new Date(alert.interval_start).toLocaleString()} />
          <Fact label="Interval end" value={new Date(alert.interval_end).toLocaleString()} />
          <Fact label="Source" value={alert.source_id} />
          <Fact label="Assignee" value={alert.assignee_name ?? "Unassigned"} />
        </dl>
      </div>

      <div className="panel p-4">
        <h2 className="text-sm font-semibold">Investigation</h2>
        {terminal ? (
          <p className="mt-2 text-sm text-slate-400">
            This alert is in a terminal status and can no longer change.
          </p>
        ) : (
          <div className="mt-3 flex flex-wrap gap-2">
            {NEXT_STATUSES.filter((next) => next !== alert.status).map((next) => (
              <button
                key={next}
                type="button"
                className="btn"
                disabled={busy}
                onClick={() =>
                  void runAction(() =>
                    api.updateAlertStatus(activeWorkspaceId, alert.id, next),
                  )
                }
              >
                {next === "false_positive" ? "Mark false positive" : `Move to ${next}`}
              </button>
            ))}
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-56">
            <label className="label" htmlFor="assignee">
              Assign to
            </label>
            <select
              id="assignee"
              className="input"
              value={alert.assignee_id ?? ""}
              disabled={busy || terminal}
              onChange={(event) =>
                void runAction(() =>
                  api.assignAlert(
                    activeWorkspaceId,
                    alert.id,
                    event.target.value === "" ? null : event.target.value,
                  ),
                )
              }
            >
              <option value="">Unassigned</option>
              {assignableMembers.map((member) => (
                <option key={member.user_id} value={member.user_id}>
                  {member.display_name} ({member.role})
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className="panel p-4">
        <h2 className="text-sm font-semibold">Comments</h2>
        {alert.comments.length === 0 ? (
          <p className="mt-2 text-sm text-slate-400">No comments yet.</p>
        ) : (
          <ul className="mt-3 space-y-3">
            {alert.comments.map((entry) => (
              <li key={entry.id} className="rounded-md border border-slate-800 p-3">
                <p className="text-sm text-slate-200">{entry.body}</p>
                <p className="mt-1 text-xs text-slate-500">
                  {entry.author_name} · {new Date(entry.created_at).toLocaleString()}
                </p>
              </li>
            ))}
          </ul>
        )}

        <form
          className="mt-4 flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            if (comment.trim() === "") return;
            void runAction(async () => {
              await api.addComment(activeWorkspaceId, alert.id, comment.trim());
              setComment("");
              return api.getAlert(activeWorkspaceId, alert.id);
            });
          }}
        >
          <div className="flex-1 min-w-56">
            <label className="label" htmlFor="comment-body">
              Add a comment
            </label>
            <input
              id="comment-body"
              className="input"
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              placeholder="What did you find?"
              maxLength={4000}
            />
          </div>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? <Spinner /> : null} Post comment
          </button>
        </form>
      </div>

      <div className="panel p-4">
        <h2 className="text-sm font-semibold">Evidence ({alert.evidence.length})</h2>
        {alert.evidence.length === 0 ? (
          <p className="mt-2 text-sm text-slate-400">No evidence linked to this alert.</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Received</th>
                  <th scope="col">IP</th>
                  <th scope="col">Route</th>
                  <th scope="col">Method</th>
                  <th scope="col">Status</th>
                  <th scope="col">Type</th>
                </tr>
              </thead>
              <tbody>
                {alert.evidence.map((item) => (
                  <tr key={item.event_id}>
                    <td className="whitespace-nowrap">
                      {new Date(item.received_at).toLocaleString()}
                    </td>
                    <td>{item.source_ip}</td>
                    <td className="font-mono text-xs">{item.route_template}</td>
                    <td>{item.method}</td>
                    <td>{item.status_code}</td>
                    <td>{item.event_type}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="panel p-4">
        <h2 className="text-sm font-semibold">History</h2>
        {alert.history.length === 0 ? (
          <p className="mt-2 text-sm text-slate-400">No history recorded yet.</p>
        ) : (
          <ol className="mt-3 space-y-2">
            {alert.history.map((entry) => (
              <li key={entry.id} className="flex flex-wrap gap-2 text-sm text-slate-300">
                <span className="font-medium">{entry.action.replace(/_/g, " ")}</span>
                {entry.from_value || entry.to_value ? (
                  <span className="text-slate-400">
                    {entry.from_value ?? "—"} → {entry.to_value ?? "—"}
                  </span>
                ) : null}
                <span className="text-xs text-slate-500">
                  {entry.actor_name ?? "system"} ·{" "}
                  {new Date(entry.created_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>

      {user ? null : <p className="text-xs text-slate-500">Session expired.</p>}
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd className="break-all text-sm text-slate-200">{value}</dd>
    </div>
  );
}
