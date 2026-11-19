import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import * as api from "../api/endpoints";
import type { ApiSource, DashboardStats } from "../api/types";
import { useAuth } from "../state/auth-context";
import { EmptyState, ErrorState, LoadingState } from "../components/States";

/** The dashboard polls on this interval. Documented in the README. */
export const DASHBOARD_POLL_INTERVAL_MS = 30_000;

const RANGE_OPTIONS = [
  { label: "Last 15 minutes", minutes: 15 },
  { label: "Last hour", minutes: 60 },
  { label: "Last 24 hours", minutes: 1440 },
  { label: "Last 7 days", minutes: 10080 },
];

export function OverviewPage() {
  const { activeWorkspaceId } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [sources, setSources] = useState<ApiSource[]>([]);
  const [rangeMinutes, setRangeMinutes] = useState(60);
  const [sourceId, setSourceId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const range = useMemo(() => {
    const end = new Date();
    const start = new Date(end.getTime() - rangeMinutes * 60_000);
    return { start: start.toISOString(), end: end.toISOString() };
  }, [rangeMinutes]);

  const load = useCallback(async () => {
    if (!activeWorkspaceId) {
      setLoading(false);
      return;
    }
    try {
      const [statsResult, sourceList] = await Promise.all([
        api.dashboardStats(
          activeWorkspaceId,
          { start: range.start, end: range.end, source_id: sourceId || undefined },
        ),
        api.listSources(activeWorkspaceId),
      ]);
      setStats(statsResult);
      setSources(sourceList);
      setError(null);
      setLastUpdated(new Date());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load the dashboard.");
    } finally {
      setLoading(false);
    }
  }, [activeWorkspaceId, range, sourceId]);

  useEffect(() => {
    setLoading(true);
    void load();
  }, [load]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void load();
    }, DASHBOARD_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  if (!activeWorkspaceId) {
    return (
      <EmptyState
        title="No workspace selected"
        description="Create a workspace to start monitoring your APIs."
      />
    );
  }

  if (loading && stats === null) {
    return <LoadingState label="Loading dashboard…" />;
  }

  if (error && stats === null) {
    return <ErrorState message={error} onRetry={() => void load()} />;
  }

  const chartData = (stats?.traffic ?? []).map((bucket) => ({
    time: new Date(bucket.bucket_start).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    }),
    Requests: bucket.total_requests,
    "Failed logins": bucket.failed_logins,
    "Access denials": bucket.access_denials,
  }));

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Overview</h1>
          <p className="text-sm text-slate-400">
            Traffic and alert counts for the selected source and time range.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="label" htmlFor="range">
              Time range
            </label>
            <select
              id="range"
              className="input w-auto"
              value={rangeMinutes}
              onChange={(event) => setRangeMinutes(Number(event.target.value))}
            >
              {RANGE_OPTIONS.map((option) => (
                <option key={option.minutes} value={option.minutes}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="source">
              Source
            </label>
            <select
              id="source"
              className="input w-auto"
              value={sourceId}
              onChange={(event) => setSourceId(event.target.value)}
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
      </div>

      {error ? (
        <p role="alert" className="text-sm text-amber-300">
          Last refresh failed: {error}
        </p>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total requests" value={stats?.total_requests ?? 0} />
        <StatCard label="Failed logins" value={stats?.failed_logins ?? 0} />
        <StatCard label="Access denials" value={stats?.access_denials ?? 0} />
        <StatCard label="Open alerts" value={stats?.open_alerts ?? 0} />
      </div>

      <div className="panel p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">Traffic</h2>
          <p className="text-xs text-slate-500">
            Buckets of {stats?.bucket_seconds ?? 60} seconds ·{" "}
            {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : "not loaded yet"}
          </p>
        </div>
        {chartData.length === 0 ? (
          <p className="py-8 text-center text-sm text-slate-400">
            No traffic recorded in this range.
          </p>
        ) : (
          <div className="h-72 w-full" data-testid="traffic-chart">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid stroke="#1f2b45" strokeDasharray="3 3" />
                <XAxis dataKey="time" stroke="#94a3b8" fontSize={12} />
                <YAxis stroke="#94a3b8" fontSize={12} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    background: "#0d1526",
                    border: "1px solid #1f2b45",
                    borderRadius: "0.5rem",
                    color: "#e2e8f0",
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="Requests"
                  stroke="#38bdf8"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="Failed logins"
                  stroke="#fb7185"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="Access denials"
                  stroke="#fbbf24"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      <p className="text-xs text-slate-500">
        {stats?.total_alerts ?? 0} alerts in this range. Alerts are investigation
        findings, not requests, and overlapping alert evidence is not summed into a
        request count.
      </p>
    </section>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="panel p-4">
      <p className="label">{label}</p>
      <p className="text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}
