/**
 * Typed wrappers around the Core API endpoints.
 */

import { apiRequest } from "./client";
import type {
  AlertDetail,
  AlertStatus,
  AlertSummary,
  ApiSource,
  ApiSourceWithKey,
  Comment,
  DashboardStats,
  EventType,
  Member,
  Page,
  SecurityEvent,
  SessionResponse,
  User,
  Workspace,
} from "./types";

export function register(input: {
  email: string;
  password: string;
  display_name: string;
}): Promise<SessionResponse> {
  return apiRequest<SessionResponse>("/api/auth/register", { method: "POST", body: input });
}

export function login(input: { email: string; password: string }): Promise<SessionResponse> {
  return apiRequest<SessionResponse>("/api/auth/login", { method: "POST", body: input });
}

export function logout(): Promise<void> {
  return apiRequest<void>("/api/auth/logout", { method: "POST" });
}

export function me(signal?: AbortSignal): Promise<User> {
  return apiRequest<User>("/api/auth/me", { signal });
}

export function listWorkspaces(signal?: AbortSignal): Promise<Workspace[]> {
  return apiRequest<Workspace[]>("/api/workspaces", { signal });
}

export function createWorkspace(name: string): Promise<Workspace> {
  return apiRequest<Workspace>("/api/workspaces", { method: "POST", body: { name } });
}

export function listMembers(workspaceId: string, signal?: AbortSignal): Promise<Member[]> {
  return apiRequest<Member[]>(`/api/workspaces/${workspaceId}/members`, { signal });
}

export function addMember(
  workspaceId: string,
  input: { email: string; role: "analyst" | "viewer" },
): Promise<Member> {
  return apiRequest<Member>(`/api/workspaces/${workspaceId}/members`, {
    method: "POST",
    body: input,
  });
}

export function listSources(workspaceId: string, signal?: AbortSignal): Promise<ApiSource[]> {
  return apiRequest<ApiSource[]>("/api/sources", { workspaceId, signal });
}

export function createSource(workspaceId: string, label: string): Promise<ApiSourceWithKey> {
  return apiRequest<ApiSourceWithKey>("/api/sources", {
    method: "POST",
    body: { label },
    workspaceId,
  });
}

export function rotateSourceKey(workspaceId: string, sourceId: string): Promise<ApiSourceWithKey> {
  return apiRequest<ApiSourceWithKey>(`/api/sources/${sourceId}/rotate`, {
    method: "POST",
    workspaceId,
  });
}

export function revokeSource(workspaceId: string, sourceId: string): Promise<ApiSource> {
  return apiRequest<ApiSource>(`/api/sources/${sourceId}/revoke`, {
    method: "POST",
    workspaceId,
  });
}

export interface EventFilters {
  start?: string | undefined;
  end?: string | undefined;
  source_id?: string | undefined;
  source_ip?: string | undefined;
  route_template?: string | undefined;
  method?: string | undefined;
  status_code?: number | undefined;
  event_type?: EventType | undefined;
  limit?: number | undefined;
  offset?: number | undefined;
}

function toQuery(filters: object): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters as Record<string, unknown>)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}
export function listEvents(
  workspaceId: string,
  filters: EventFilters,
  signal?: AbortSignal,
): Promise<Page<SecurityEvent>> {
  return apiRequest<Page<SecurityEvent>>(`/api/events${toQuery(filters)}`, {
    workspaceId,
    signal,
  });
}

export function dashboardStats(
  workspaceId: string,
  filters: { start?: string | undefined; end?: string | undefined; source_id?: string | undefined },
  signal?: AbortSignal,
): Promise<DashboardStats> {
  return apiRequest<DashboardStats>(`/api/dashboard/stats${toQuery(filters)}`, {
    workspaceId,
    signal,
  });
}

export interface AlertFilters {
  status_filter?: AlertStatus | undefined;
  severity?: string | undefined;
  source_id?: string | undefined;
  start?: string | undefined;
  end?: string | undefined;
  limit?: number | undefined;
  offset?: number | undefined;
}

export function listAlerts(
  workspaceId: string,
  filters: AlertFilters,
  signal?: AbortSignal,
): Promise<Page<AlertSummary>> {
  return apiRequest<Page<AlertSummary>>(`/api/alerts${toQuery(filters)}`, {
    workspaceId,
    signal,
  });
}

export function getAlert(
  workspaceId: string,
  alertId: string,
  signal?: AbortSignal,
): Promise<AlertDetail> {
  return apiRequest<AlertDetail>(`/api/alerts/${alertId}`, { workspaceId, signal });
}

export function updateAlertStatus(
  workspaceId: string,
  alertId: string,
  status: AlertStatus,
): Promise<AlertDetail> {
  return apiRequest<AlertDetail>(`/api/alerts/${alertId}/status`, {
    method: "PATCH",
    body: { status },
    workspaceId,
  });
}

export function assignAlert(
  workspaceId: string,
  alertId: string,
  assigneeId: string | null,
): Promise<AlertDetail> {
  return apiRequest<AlertDetail>(`/api/alerts/${alertId}/assignee`, {
    method: "PATCH",
    body: { assignee_id: assigneeId },
    workspaceId,
  });
}

export function addComment(workspaceId: string, alertId: string, body: string): Promise<Comment> {
  return apiRequest<Comment>(`/api/alerts/${alertId}/comments`, {
    method: "POST",
    body: { body },
    workspaceId,
  });
}
