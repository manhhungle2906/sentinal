import { createContext, useContext } from "react";
import type { User, Workspace } from "../api/types";

/**
 * The authentication state shared by the whole application.
 *
 * The context object lives in its own module so the provider file only
 * exports components, which keeps React Fast Refresh working.
 */
export interface AuthState {
  user: User | null;
  workspaces: Workspace[];
  activeWorkspaceId: string | null;
  loading: boolean;
  error: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, displayName: string) => Promise<void>;
  signOut: () => Promise<void>;
  selectWorkspace: (workspaceId: string) => void;
  refreshWorkspaces: () => Promise<void>;
  createWorkspace: (name: string) => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);

/** Access the authentication state. Must be called inside an AuthProvider. */
export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth must be used inside an AuthProvider");
  }
  return context;
}
