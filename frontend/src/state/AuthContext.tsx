import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import * as api from "../api/endpoints";
import { ApiError } from "../api/client";
import { AuthContext } from "./auth-context";
import type { AuthState } from "./auth-context";
import type { User, Workspace } from "../api/types";

const WORKSPACE_STORAGE_KEY = "sentinel.workspace";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadWorkspaces = useCallback(async () => {
    const list = await api.listWorkspaces();
    setWorkspaces(list);
    setActiveWorkspaceId((current) => {
      if (current && list.some((workspace) => workspace.id === current)) {
        return current;
      }
      const stored = window.localStorage.getItem(WORKSPACE_STORAGE_KEY);
      if (stored && list.some((workspace) => workspace.id === stored)) {
        return stored;
      }
      return list[0]?.id ?? null;
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const current = await api.me();
        if (cancelled) return;
        setUser(current);
        await loadWorkspaces();
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 401) {
          if (!cancelled) {
            setUser(null);
            setWorkspaces([]);
          }
        } else if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Could not load the session.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadWorkspaces]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      const session = await api.login({ email, password });
      setUser(session.user);
      await loadWorkspaces();
    },
    [loadWorkspaces],
  );

  const signUp = useCallback(
    async (email: string, password: string, displayName: string) => {
      const session = await api.register({
        email,
        password,
        display_name: displayName,
      });
      setUser(session.user);
      await loadWorkspaces();
    },
    [loadWorkspaces],
  );

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
      setWorkspaces([]);
      setActiveWorkspaceId(null);
      window.localStorage.removeItem(WORKSPACE_STORAGE_KEY);
    }
  }, []);

  const selectWorkspace = useCallback((workspaceId: string) => {
    setActiveWorkspaceId(workspaceId);
    window.localStorage.setItem(WORKSPACE_STORAGE_KEY, workspaceId);
  }, []);

  const createWorkspace = useCallback(
    async (name: string) => {
      const workspace = await api.createWorkspace(name);
      await loadWorkspaces();
      selectWorkspace(workspace.id);
    },
    [loadWorkspaces, selectWorkspace],
  );

  const value = useMemo<AuthState>(
    () => ({
      user,
      workspaces,
      activeWorkspaceId,
      loading,
      error,
      signIn,
      signUp,
      signOut,
      selectWorkspace,
      refreshWorkspaces: loadWorkspaces,
      createWorkspace,
    }),
    [
      user,
      workspaces,
      activeWorkspaceId,
      loading,
      error,
      signIn,
      signUp,
      signOut,
      selectWorkspace,
      loadWorkspaces,
      createWorkspace,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
