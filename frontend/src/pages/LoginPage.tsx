import { useState } from "react";
import type { FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../state/auth-context";
import { Spinner } from "../components/States";

export function LoginPage() {
  const { user, signIn, signUp } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) {
    return <Navigate to="/" replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "login") {
        await signIn(email, password);
      } else {
        await signUp(email, password, displayName);
      }
      navigate("/");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Sign in failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="panel w-full max-w-md p-8">
        <h1 className="text-2xl font-bold text-sky-300">API Sentinel</h1>
        <p className="mt-1 text-sm text-slate-400">
          Sign in to monitor your APIs and investigate alerts.
        </p>

        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          {mode === "register" ? (
            <div>
              <label className="label" htmlFor="display-name">
                Display name
              </label>
              <input
                id="display-name"
                className="input"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                required
                autoComplete="name"
              />
            </div>
          ) : null}

          <div>
            <label className="label" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              className="input"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              autoComplete="email"
            />
          </div>

          <div>
            <label className="label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              className="input"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={mode === "register" ? 10 : 1}
              autoComplete={mode === "register" ? "new-password" : "current-password"}
            />
            {mode === "register" ? (
              <p className="mt-1 text-xs text-slate-500">At least 10 characters.</p>
            ) : null}
          </div>

          {error ? (
            <p role="alert" className="text-sm text-rose-300">
              {error}
            </p>
          ) : null}

          <button type="submit" className="btn btn-primary w-full justify-center" disabled={submitting}>
            {submitting ? <Spinner /> : null}
            {mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>

        <button
          type="button"
          className="mt-4 text-sm text-sky-300 underline-offset-2 hover:underline"
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setError(null);
          }}
        >
          {mode === "login"
            ? "Need an account? Register instead"
            : "Already registered? Sign in instead"}
        </button>
      </div>
    </div>
  );
}
