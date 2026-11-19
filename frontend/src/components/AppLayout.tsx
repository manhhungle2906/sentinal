import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../state/auth-context";

const NAV_ITEMS = [
  { to: "/", label: "Overview", end: true },
  { to: "/events", label: "Events", end: false },
  { to: "/alerts", label: "Alerts", end: false },
  { to: "/sources", label: "Sources", end: false },
  { to: "/team", label: "Team", end: false },
];

export function AppLayout() {
  const { user, workspaces, activeWorkspaceId, selectWorkspace, signOut } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-800 bg-slate-950/80">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-4 py-3">
          <span className="text-lg font-bold tracking-tight text-sky-300">API Sentinel</span>

          <nav aria-label="Main navigation" className="flex flex-wrap items-center gap-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `rounded-md px-3 py-1.5 text-sm font-medium ${
                    isActive
                      ? "bg-sky-900/60 text-sky-200"
                      : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm">
              <span className="text-slate-400">Workspace</span>
              <select
                aria-label="Workspace"
                className="input w-auto"
                value={activeWorkspaceId ?? ""}
                onChange={(event) => selectWorkspace(event.target.value)}
                disabled={workspaces.length === 0}
              >
                {workspaces.length === 0 ? (
                  <option value="">No workspace yet</option>
                ) : (
                  workspaces.map((workspace) => (
                    <option key={workspace.id} value={workspace.id}>
                      {workspace.name}
                    </option>
                  ))
                )}
              </select>
            </label>
            <span className="hidden text-sm text-slate-400 sm:inline">{user?.email}</span>
            <button
              type="button"
              className="btn"
              onClick={() => {
                void signOut().then(() => navigate("/login"));
              }}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
