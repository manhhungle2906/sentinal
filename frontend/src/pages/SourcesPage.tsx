import { useCallback, useEffect, useState } from "react";
import * as api from "../api/endpoints";
import type { ApiSource, ApiSourceWithKey } from "../api/types";
import { useAuth } from "../state/auth-context";
import { EmptyState, ErrorState, LoadingState, Spinner } from "../components/States";

export function SourcesPage() {
  const { activeWorkspaceId, workspaces } = useAuth();
  const [sources, setSources] = useState<ApiSource[]>([]);
  const [label, setLabel] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<ApiSourceWithKey | null>(null);

  const load = useCallback(async () => {
    if (!activeWorkspaceId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      setSources(await api.listSources(activeWorkspaceId));
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load the sources.");
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
        description="Create a workspace before adding a monitored API source."
        action={
          <CreateWorkspaceButton />
        }
      />
    );
  }

  async function createSource(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!activeWorkspaceId || label.trim() === "") return;
    setBusy(true);
    setActionError(null);
    try {
      const source = await api.createSource(activeWorkspaceId, label.trim());
      setCreated(source);
      setLabel("");
      await load();
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "Could not create the source.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold">Monitored API sources</h1>
        <p className="text-sm text-slate-400">
          Each source authenticates with its own ingestion key. The raw key is shown
          once, when the source is created or rotated.
        </p>
      </div>

      {created ? (
        <div className="panel border-emerald-800 bg-emerald-950/30 p-4">
          <p className="text-sm font-semibold text-emerald-200">
            Copy the ingestion key now — it is not shown again.
          </p>
          <code className="mt-2 block break-all rounded bg-slate-950 p-3 text-xs text-emerald-100">
            {created.ingestion_key}
          </code>
          <button
            type="button"
            className="btn mt-3"
            onClick={() => {
              void navigator.clipboard?.writeText(created.ingestion_key);
            }}
          >
            Copy key
          </button>
        </div>
      ) : null}

      <form className="panel flex flex-wrap items-end gap-3 p-4" onSubmit={createSource}>
        <div className="flex-1 min-w-56">
          <label className="label" htmlFor="source-label">
            Source label
          </label>
          <input
            id="source-label"
            className="input"
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            placeholder="Demo API"
            required
            maxLength={120}
          />
        </div>
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? <Spinner /> : null} Create source
        </button>
      </form>

      {actionError ? (
        <p role="alert" className="text-sm text-rose-300">
          {actionError}
        </p>
      ) : null}
      {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}

      {loading && sources.length === 0 ? (
        <LoadingState label="Loading sources…" />
      ) : sources.length === 0 ? (
        <EmptyState
          title="No sources yet"
          description="Create a source to get an ingestion key, then point your API at the ingestion endpoint."
        />
      ) : (
        <div className="panel overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Label</th>
                <th scope="col">Key prefix</th>
                <th scope="col">Created</th>
                <th scope="col">State</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((source) => (
                <tr key={source.id}>
                  <td>{source.label}</td>
                  <td className="font-mono text-xs">{source.key_prefix}</td>
                  <td>{new Date(source.created_at).toLocaleString()}</td>
                  <td>
                    {source.is_active ? (
                      <span className="badge badge-success">Active</span>
                    ) : (
                      <span className="badge badge-neutral">Revoked</span>
                    )}
                  </td>
                  <td className="space-x-2">
                    <button
                      type="button"
                      className="btn"
                      disabled={busy}
                      onClick={() => {
                        setBusy(true);
                        setActionError(null);
                        void api
                          .rotateSourceKey(activeWorkspaceId, source.id)
                          .then((rotated) => {
                            setCreated(rotated);
                            return load();
                          })
                          .catch((caught: unknown) =>
                            setActionError(
                              caught instanceof Error ? caught.message : "Rotation failed.",
                            ),
                          )
                          .finally(() => setBusy(false));
                      }}
                    >
                      Rotate key
                    </button>
                    {source.is_active ? (
                      <button
                        type="button"
                        className="btn"
                        disabled={busy}
                        onClick={() => {
                          setBusy(true);
                          setActionError(null);
                          void api
                            .revokeSource(activeWorkspaceId, source.id)
                            .then(() => load())
                            .catch((caught: unknown) =>
                              setActionError(
                                caught instanceof Error ? caught.message : "Revoke failed.",
                              ),
                            )
                            .finally(() => setBusy(false));
                        }}
                      >
                        Revoke
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {workspaces.length === 0 ? <CreateWorkspaceButton /> : null}
    </section>
  );
}

function CreateWorkspaceButton() {
  const { createWorkspace } = useAuth();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  return (
    <form
      className="panel flex flex-wrap items-end gap-3 p-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (name.trim() === "") return;
        void createWorkspace(name.trim())
          .then(() => setName(""))
          .catch((caught: unknown) =>
            setError(caught instanceof Error ? caught.message : "Could not create the workspace."),
          );
      }}
    >
      <div className="flex-1 min-w-56">
        <label className="label" htmlFor="workspace-name">
          New workspace name
        </label>
        <input
          id="workspace-name"
          className="input"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Acme Security"
          required
          maxLength={120}
        />
      </div>
      <button type="submit" className="btn btn-primary">
        Create workspace
      </button>
      {error ? (
        <p role="alert" className="w-full text-sm text-rose-300">
          {error}
        </p>
      ) : null}
    </form>
  );
}
