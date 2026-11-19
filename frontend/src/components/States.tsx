import type { ReactNode } from "react";

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="p-6 text-sm text-slate-400">
      {label}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="panel border-rose-800 bg-rose-950/40 p-4 text-sm text-rose-200"
    >
      <p className="font-semibold">Something went wrong</p>
      <p className="mt-1 text-rose-200/90">{message}</p>
      {onRetry ? (
        <button type="button" className="btn mt-3" onClick={onRetry}>
          Try again
        </button>
      ) : null}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="panel p-8 text-center">
      <p className="text-base font-semibold text-slate-200">{title}</p>
      <p className="mx-auto mt-2 max-w-md text-sm text-slate-400">{description}</p>
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}

export function Spinner() {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-500 border-t-transparent"
    />
  );
}
