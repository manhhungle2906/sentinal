/**
 * Shared API contract types. These mirror the Core API DTOs exactly.
 */

export type WorkspaceRole = "owner" | "analyst" | "viewer";

export type AlertStatus = "new" | "investigating" | "resolved" | "false_positive";

export type AlertSeverity = "low" | "medium" | "high" | "critical";

export type EventType = "request" | "login_failed";

export interface User {
  id: string;
  email: string;
  display_name: string;
  created_at: string;
}

export interface SessionResponse {
  user: User;
  expires_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  role: WorkspaceRole;
  created_at: string;
}

export interface Member {
  user_id: string;
  email: string;
  display_name: string;
  role: WorkspaceRole;
  joined_at: string;
}

export interface ApiSource {
  id: string;
  workspace_id: string;
  label: string;
  key_prefix: string;
  created_at: string;
  revoked_at: string | null;
  is_active: boolean;
}

export interface ApiSourceWithKey extends ApiSource {
  ingestion_key: string;
}

export interface SecurityEvent {
  id: string;
  event_uuid: string;
  source_id: string;
  source_label: string | null;
  received_at: string;
  request_at: string | null;
  source_ip: string;
  route_template: string;
  method: string;
  status_code: number;
  duration_ms: number | null;
  event_type: EventType;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface TrafficBucket {
  bucket_start: string;
  total_requests: number;
  failed_logins: number;
  access_denials: number;
}

export interface DashboardStats {
  source_id: string | null;
  range_start: string;
  range_end: string;
  total_requests: number;
  failed_logins: number;
  access_denials: number;
  open_alerts: number;
  total_alerts: number;
  bucket_seconds: number;
  traffic: TrafficBucket[];
}

export interface AlertSummary {
  id: string;
  workspace_id: string;
  source_id: string;
  source_label: string | null;
  rule_key: string;
  severity: AlertSeverity;
  status: AlertStatus;
  source_ip: string;
  count_at_trigger: number;
  threshold: number;
  window_seconds: number;
  interval_start: string;
  interval_end: string;
  assignee_id: string | null;
  assignee_name: string | null;
  created_at: string;
  updated_at: string;
  evidence_count: number;
}

export interface Evidence {
  event_id: string;
  event_uuid: string;
  received_at: string;
  request_at: string | null;
  source_ip: string;
  route_template: string;
  method: string;
  status_code: number;
  duration_ms: number | null;
  event_type: EventType;
}

export interface Comment {
  id: string;
  author_id: string;
  author_name: string;
  body: string;
  created_at: string;
}

export interface HistoryEntry {
  id: string;
  action: string;
  actor_id: string | null;
  actor_name: string | null;
  from_value: string | null;
  to_value: string | null;
  created_at: string;
}

export interface AlertDetail {
  id: string;
  workspace_id: string;
  source_id: string;
  rule_key: string;
  severity: AlertSeverity;
  status: AlertStatus;
  source_ip: string;
  count_at_trigger: number;
  threshold: number;
  window_seconds: number;
  interval_start: string;
  interval_end: string;
  assignee_id: string | null;
  assignee_name: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  evidence: Evidence[];
  comments: Comment[];
  history: HistoryEntry[];
}

export const RULE_DESCRIPTIONS: Record<string, string> = {
  failed_login_burst:
    "Explicit login_failed events from the same source and source IP reaching the threshold within the window.",
  high_request_volume:
    "All validated request events from the same source and source IP reaching the threshold within the window.",
  repeated_access_denial:
    "HTTP 401/403 responses outside the failed-login stream from the same source and source IP reaching the threshold within the window.",
};

export function isOpen(status: AlertStatus): boolean {
  return status === "new" || status === "investigating";
}

export function isTerminal(status: AlertStatus): boolean {
  return status === "resolved" || status === "false_positive";
}

export function statusLabel(status: AlertStatus): string {
  switch (status) {
    case "new":
      return "New";
    case "investigating":
      return "Investigating";
    case "resolved":
      return "Resolved";
    case "false_positive":
      return "False positive";
  }
}

export function severityLabel(severity: AlertSeverity): string {
  switch (severity) {
    case "low":
      return "Low";
    case "medium":
      return "Medium";
    case "high":
      return "High";
    case "critical":
      return "Critical";
  }
}
