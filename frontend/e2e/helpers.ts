/**
 * Test helpers for the API Sentinel browser checks.
 *
 * The helpers talk to the real Core and Ingest APIs so the browser tests
 * exercise genuine data. No credentials are hard-coded beyond the throwaway
 * accounts created inside the isolated test stack.
 */

import { randomUUID } from "node:crypto";
import { expect } from "@playwright/test";
import type { Page } from "@playwright/test";

export const CORE_URL = process.env.E2E_CORE_URL ?? "http://localhost:8000";
export const INGEST_URL = process.env.E2E_INGEST_URL ?? "http://localhost:8001";

/**
 * A unique event id.
 *
 * The ingestion API requires a UUID, so the identifier is a random UUIDv4.
 */
export function newEventId(): string {
  return randomUUID();
}

export interface ApiSession {
  cookie: string;
  csrf: string;
  userId: string;
}

export interface ApiResponse<T> {
  status: number;
  body: T;
}

function readSetCookie(headers: Headers): string[] {
  const raw = headers.getSetCookie?.() ?? [];
  if (raw.length > 0) {
    return raw;
  }
  const single = headers.get("set-cookie");
  return single ? [single] : [];
}

function parseCookies(headers: Headers): { cookie: string; csrf: string } {
  const cookies = readSetCookie(headers);
  const parts: string[] = [];
  let csrf = "";
  for (const entry of cookies) {
    const [pair] = entry.split(";");
    if (!pair) continue;
    const [name, ...rest] = pair.split("=");
    const value = rest.join("=");
    parts.push(`${name}=${value}`);
    if (name.trim() === "sentinel_csrf") {
      csrf = value;
    }
  }
  return { cookie: parts.join("; "), csrf };
}

export async function apiRequest<T>(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    session?: ApiSession;
    workspaceId?: string;
  } = {},
): Promise<ApiResponse<T>> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (options.session) {
    headers.Cookie = options.session.cookie;
    if (method !== "GET" && method !== "HEAD" && options.session.csrf) {
      headers["X-CSRF-Token"] = options.session.csrf;
    }
  }
  if (options.workspaceId) {
    headers["X-Workspace-Id"] = options.workspaceId;
  }

  const response = await fetch(`${CORE_URL}${path}`, {
    method,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    redirect: "manual",
  });
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  return { status: response.status, body: body as T };
}

/**
 * Register a throwaway account, or sign in when it already exists.
 *
 * The browser suite must be repeatable against a stack that already holds the
 * accounts from a previous run.
 */
export async function registerUser(
  email: string,
  password: string,
  displayName: string,
): Promise<ApiSession> {
  const response = await fetch(`${CORE_URL}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, display_name: displayName }),
  });
  if (response.status === 201) {
    const { cookie, csrf } = parseCookies(response.headers);
    const body = (await response.json()) as { user: { id: string } };
    return { cookie, csrf, userId: body.user.id };
  }
  if (response.status === 409) {
    return loginUser(email, password);
  }
  throw new Error(
    `could not register ${email}: ${response.status} ${await response.text()}`,
  );
}

export async function loginUser(email: string, password: string): Promise<ApiSession> {
  const response = await fetch(`${CORE_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (response.status !== 200) {
    throw new Error(
      `could not sign in ${email}: ${response.status} ${await response.text()}`,
    );
  }
  const { cookie, csrf } = parseCookies(response.headers);
  const body = (await response.json()) as { user: { id: string } };
  return { cookie, csrf, userId: body.user.id };
}

/** Submit one event record to the ingestion API. */
export async function ingestEvent(
  key: string,
  payload: {
    event_id: string;
    event_type?: string;
    occurred_at?: string;
    source_ip: string;
    route_template: string;
    method: string;
    status_code: number;
    duration_ms?: number;
  },
): Promise<number> {
  const response = await fetch(`${INGEST_URL}/ingest/v1/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Source-Key": key },
    body: JSON.stringify(payload),
  });
  return response.status;
}

/** Wait until the detector produced an alert for the given rule key. */
export async function waitForAlert(
  session: ApiSession,
  workspaceId: string,
  ruleKey: string,
  timeoutMs = 60_000,
): Promise<string | null> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const response = await apiRequest<{
      items: { id: string; rule_key: string }[];
    }>("/api/alerts", { session, workspaceId });
    if (response.status === 200 && response.body.items) {
      const match = response.body.items.find((item) => item.rule_key === ruleKey);
      if (match) {
        return match.id;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  return null;
}

/**
 * Wait until an alert row for the rule key is visible in the alerts table.
 *
 * The detector processes events asynchronously, so the browser view can lag
 * behind the API. The helper re-reads the list through the Refresh button
 * until the row shows up or the timeout expires.
 */
export async function expectAlertRow(
  page: Page,
  ruleKey: string,
  timeoutMs = 90_000,
): Promise<void> {
  await expectAlertRowText(page, ruleKey, timeoutMs);
}

/**
 * Wait until an alerts-table row containing the given text is visible.
 */
export async function expectAlertRowText(
  page: Page,
  text: string,
  timeoutMs = 90_000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const row = page.getByRole("row").filter({ hasText: text }).first();
    if (await row.isVisible().catch(() => false)) {
      await expect(row).toBeVisible();
      return;
    }
    const refresh = page.getByRole("button", { name: "Refresh" });
    if (await refresh.isVisible().catch(() => false)) {
      await refresh.click();
    } else {
      await page.reload();
    }
    await page.waitForTimeout(1000);
  }
  await expect(page.getByRole("row").filter({ hasText: text }).first()).toBeVisible();
}
