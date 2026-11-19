import type { AlertSeverity, AlertStatus } from "../api/types";
import { severityLabel, statusLabel } from "../api/types";

const STATUS_CLASS: Record<AlertStatus, string> = {
  new: "badge badge-danger",
  investigating: "badge badge-warning",
  resolved: "badge badge-success",
  false_positive: "badge badge-neutral",
};

const SEVERITY_CLASS: Record<AlertSeverity, string> = {
  low: "badge badge-neutral",
  medium: "badge badge-info",
  high: "badge badge-warning",
  critical: "badge badge-danger",
};

export function StatusBadge({ status }: { status: AlertStatus }) {
  return <span className={STATUS_CLASS[status]}>{statusLabel(status)}</span>;
}

export function SeverityBadge({ severity }: { severity: AlertSeverity }) {
  return <span className={SEVERITY_CLASS[severity]}>{severityLabel(severity)}</span>;
}
