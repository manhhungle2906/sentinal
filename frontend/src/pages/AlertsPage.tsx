import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import * as api from "../api/endpoints";
import type { AlertStatus, AlertSummary, ApiSource } from "../api/types";
import { useAuth } from "../state/auth-context";
import { SeverityBadge, StatusBadge } from "../components/Badges";
import { EmptyState, ErrorState, LoadingState } from "../components/States";

const PAGE_SIZE = 25;

/** The alerts page polls on this interval. Documented in the README. */
export const ALERTS_POLL_INTERVAL_MS = 15_000;

const STATUS_FILTERS: AlertStatus[] = ["new", "investigating", "resolved", "false_positive"];
const SEVERITIES = ["low", "medium", "high", "critical"];

export function AlertsPage() {
  const { activeWorkspaceId } = useAuth();
  const [alerts, setAlerts] = useState<AlertSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [sources, setSources] = useState<ApiSource[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (silent = false) => {
    if (!activeWorkspaceId) {
      setLoading(false);
      return;
    }
    if (!silent) {
      setLoading(true);
    }
    try {
      const page = await api.listAlerts(activeWorkspaceId, {
        status_filter: statusFilter ? (statusFilter as AlertStatus) : undefined,
        severity: severityFilter || undefined,
        source_id: sourceFilter || undefined,
        limit: PAGE_SIZE,
        offset,
      });
      setAlerts(page.items);
      setTotal(page.total);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load the alerts.");
    } finally {
      setLoading(false);
    }
  }, [activeWorkspaceId, statusFilter, severityFilter, sourceFilter, offset]);

  useEffect(() => {
    void load();
  }, [load]);

  // Poll so newly detected alerts appear without a manual reload.
  useEffect(() => {
    const timer = window.setInterval(() => {
      void load(true);
    }, ALERTS_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  useEffect(() => {
    if (!activeWorkspaceId) return;
    void api
      .listSources(activeWorkspaceId)
      .then(setSources)
      .catch(() => setSources([]));
  }, [activeWorkspaceId]);

  if (!activeWorkspaceId) {
    return (
      <EmptyState
        title="No workspace selected"
        description="Create a workspace to review alerts."
      />
    );
  }

  return (
    <section className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Alerts</h1>
        <p className="text-sm text-slate-400">
          Rule findings for this workspace. Open an alert to inspect its evidence and
          investigation history.
        </p>
      </div>

      <div className="panel flex flex-wrap items-end gap-3 p-4">
        <div>
          <label className="label" htmlFor="alert-status">
            Status
          </label>
          <select
            id="alert-status"
            className="input w-auto"
            value={statusFilter}
            onChange={(event) => {
              setStatusFilter(event.target.value);
              setOffset(0);
            }}
          >
            <option value="">All statuses</option>
            {STATUS_FILTERS.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="alert-severity">
            Severity
          </label>
          <select
            id="alert-severity"
            className="input w-auto"
            value={severityFilter}
            onChange={(event) => {
              setSeverityFilter(event.target.value);
              setOffset(0);
            }}
          >
            <option value="">All severities</option>
            {SEVERITIES.map((severity) => (
              <option key={severity} value={severity}>
                {severity}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="alert-source">
            Source
          </label>
          <select
            id="alert-source"
            className="input w-auto"
            value={sourceFilter}
            onChange={(event) => {
              setSourceFilter(event.target.value);
              setOffset(0);
            }}
          >
            <option value="">All sources</option>
            {sources.map((source) => (
              <option key={source.id} value={source.id}>
                {source.label}
              </option>
            ))}
          </select>
        </div>
        <button type="button" className="btn" onClick={() => void load()}>
          Refresh
        </button>
      </div>

      {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}

      {loading && alerts.length === 0 ? (
        <LoadingState label="Loading alerts…" />
      ) : alerts.length === 0 ? (
        <EmptyState
          title="No alerts match these filters"
          description="Alerts appear here when a detection rule crosses its threshold. Try another status or severity."
        />
      ) : (
        <div className="panel overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Raised</th>
                <th scope="col">Rule</th>
                <th scope="col">Severity</th>
                <th scope="col">Status</th>
                <th scope="col">Source IP</th>
                <th scope="col">Count</th>
                <th scope="col">Assignee</th>
                <th scope="col">Evidence</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((alert) => (
                <tr key={alert.id}>
                  <td className="whitespace-nowrap">
                    <Link
                      className="text-sky-300 underline-offset-2 hover:underline"
                      to={`/alerts/${alert.id}`}
                    >
                      {new Date(alert.created_at).toLocaleString()}
                    </Link>
                  </td>
                  <td className="font-mono text-xs">{alert.rule_key}</td>
                  <td>
                    <SeverityBadge severity={alert.severity} />
                  </td>
                  <td>
                    <StatusBadge status={alert.status} />
                  </td>
                  <td>{alert.source_ip}</td>
                  <td>
                    {alert.count_at_trigger} / {alert.threshold}
                  </td>
                  <td>{alert.assignee_name ?? "Unassigned"}</td>
                  <td>{alert.evidence_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-center justify-between text-sm text-slate-400">
        <span>
          Showing {alerts.length} of {total} alerts
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            className="btn"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </button>
          <button
            type="button"
            className="btn"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </button>
        </div>
      </div>
    </section>
  );
}
