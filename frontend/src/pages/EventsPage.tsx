import { useCallback, useEffect, useState } from "react";
import * as api from "../api/endpoints";
import type { ApiSource, EventType, SecurityEvent } from "../api/types";
import { useAuth } from "../state/auth-context";
import { EmptyState, ErrorState, LoadingState } from "../components/States";

const PAGE_SIZE = 25;

const METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"];
const EVENT_TYPES: EventType[] = ["request", "login_failed"];

interface Filters {
  source_id: string;
  source_ip: string;
  route_template: string;
  method: string;
  status_code: string;
  event_type: string;
}

const EMPTY_FILTERS: Filters = {
  source_id: "",
  source_ip: "",
  route_template: "",
  method: "",
  status_code: "",
  event_type: "",
};

function toLocalInputValue(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

export function EventsPage() {
  const { activeWorkspaceId } = useAuth();
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [applied, setApplied] = useState<Filters>(EMPTY_FILTERS);
  const [start, setStart] = useState(() =>
    toLocalInputValue(new Date(Date.now() - 60 * 60_000)),
  );
  const [end, setEnd] = useState(() => toLocalInputValue(new Date()));
  const [appliedRange, setAppliedRange] = useState({ start, end });
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [sources, setSources] = useState<ApiSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!activeWorkspaceId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const page = await api.listEvents(activeWorkspaceId, {
        start: new Date(appliedRange.start).toISOString(),
        end: new Date(appliedRange.end).toISOString(),
        source_id: applied.source_id || undefined,
        source_ip: applied.source_ip || undefined,
        route_template: applied.route_template || undefined,
        method: applied.method || undefined,
        status_code: applied.status_code ? Number(applied.status_code) : undefined,
        event_type: (applied.event_type as EventType | undefined) || undefined,
        limit: PAGE_SIZE,
        offset,
      });
      setEvents(page.items);
      setTotal(page.total);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load the events.");
    } finally {
      setLoading(false);
    }
  }, [activeWorkspaceId, applied, appliedRange, offset]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!activeWorkspaceId) return;
    void api
      .listSources(activeWorkspaceId)
      .then(setSources)
      .catch(() => setSources([]));
  }, [activeWorkspaceId]);

  function resetFilters() {
    const now = new Date();
    const oneHourAgo = new Date(now.getTime() - 60 * 60_000);
    const nextStart = toLocalInputValue(oneHourAgo);
    const nextEnd = toLocalInputValue(now);
    setFilters(EMPTY_FILTERS);
    setApplied(EMPTY_FILTERS);
    setStart(nextStart);
    setEnd(nextEnd);
    setAppliedRange({ start: nextStart, end: nextEnd });
    setOffset(0);
  }

  if (!activeWorkspaceId) {
    return (
      <EmptyState
        title="No workspace selected"
        description="Create a workspace to start exploring events."
      />
    );
  }

  return (
    <section className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Event explorer</h1>
        <p className="text-sm text-slate-400">
          Filter the recorded request metadata for this workspace.
        </p>
      </div>

      <form
        className="panel grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4"
        onSubmit={(event) => {
          event.preventDefault();
          setApplied(filters);
          setAppliedRange({ start, end });
          setOffset(0);
        }}
      >
        <div>
          <label className="label" htmlFor="event-start">
            From
          </label>
          <input
            id="event-start"
            type="datetime-local"
            className="input"
            value={start}
            onChange={(event) => setStart(event.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="event-end">
            To
          </label>
          <input
            id="event-end"
            type="datetime-local"
            className="input"
            value={end}
            onChange={(event) => setEnd(event.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="event-source">
            Source
          </label>
          <select
            id="event-source"
            className="input"
            value={filters.source_id}
            onChange={(event) => setFilters({ ...filters, source_id: event.target.value })}
          >
            <option value="">All sources</option>
            {sources.map((source) => (
              <option key={source.id} value={source.id}>
                {source.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="event-ip">
            Source IP
          </label>
          <input
            id="event-ip"
            className="input"
            placeholder="203.0.113.10"
            value={filters.source_ip}
            onChange={(event) => setFilters({ ...filters, source_ip: event.target.value })}
          />
        </div>
        <div>
          <label className="label" htmlFor="event-route">
            Route
          </label>
          <input
            id="event-route"
            className="input"
            placeholder="/api/products"
            value={filters.route_template}
            onChange={(event) => setFilters({ ...filters, route_template: event.target.value })}
          />
        </div>
        <div>
          <label className="label" htmlFor="event-method">
            Method
          </label>
          <select
            id="event-method"
            className="input"
            value={filters.method}
            onChange={(event) => setFilters({ ...filters, method: event.target.value })}
          >
            <option value="">Any method</option>
            {METHODS.map((method) => (
              <option key={method} value={method}>
                {method}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="event-status">
            Status code
          </label>
          <input
            id="event-status"
            className="input"
            inputMode="numeric"
            placeholder="200"
            value={filters.status_code}
            onChange={(event) => setFilters({ ...filters, status_code: event.target.value })}
          />
        </div>
        <div>
          <label className="label" htmlFor="event-type">
            Event type
          </label>
          <select
            id="event-type"
            className="input"
            value={filters.event_type}
            onChange={(event) => setFilters({ ...filters, event_type: event.target.value })}
          >
            <option value="">Any type</option>
            {EVENT_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-end gap-2 lg:col-span-4">
          <button type="submit" className="btn btn-primary">
            Apply filters
          </button>
          <button type="button" className="btn" onClick={resetFilters}>
            Reset filters
          </button>
          <button type="button" className="btn" onClick={() => void load()}>
            Refresh
          </button>
        </div>
      </form>

      {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}

      {loading && events.length === 0 ? (
        <LoadingState label="Loading events…" />
      ) : events.length === 0 ? (
        <EmptyState
          title="No events match these filters"
          description="Widen the time range or reset the filters. Events appear here after the source submits them to the ingestion API."
        />
      ) : (
        <div className="panel overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Received</th>
                <th scope="col">Source</th>
                <th scope="col">IP</th>
                <th scope="col">Route</th>
                <th scope="col">Method</th>
                <th scope="col">Status</th>
                <th scope="col">Duration</th>
                <th scope="col">Type</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id}>
                  <td className="whitespace-nowrap">
                    {new Date(event.received_at).toLocaleString()}
                  </td>
                  <td>{event.source_label ?? event.source_id}</td>
                  <td>{event.source_ip}</td>
                  <td className="font-mono text-xs">{event.route_template}</td>
                  <td>{event.method}</td>
                  <td>{event.status_code}</td>
                  <td>{event.duration_ms === null ? "—" : `${event.duration_ms} ms`}</td>
                  <td>{event.event_type}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-center justify-between text-sm text-slate-400">
        <span>
          Showing {events.length} of {total} events
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
