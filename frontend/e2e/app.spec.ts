import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import {
  apiRequest,
  expectAlertRow,
  expectAlertRowText,
  ingestEvent,
  newEventId,
  registerUser,
} from "./helpers";

/**
 * The browser walkthrough covers the required release path:
 * register -> workspace -> source -> real event -> detection -> investigation
 * with two members, and a non-member that cannot see the data.
 *
 * The suite runs serially because the members share one workspace and one
 * alert; each test uses its own account where the scenario needs it.
 */

const PASSWORD = "e2e-password-12345";
const OWNER_EMAIL = "e2e-owner@example.com";
const ANALYST_EMAIL = "e2e-analyst@example.com";
const OUTSIDER_EMAIL = "e2e-outsider@example.com";
const WORKSPACE_NAME = "E2E Workspace";

/**
 * Every run uses its own reserved documentation IPs so the detection counts
 * start from zero even when the suite runs against a stack that already
 * holds the events of a previous run.
 */
const RUN_BASE = 32 + Math.floor(Math.random() * 120);
const IP_ORDINARY = `203.0.113.${RUN_BASE}`;
const IP_FILTERED = `203.0.113.${RUN_BASE + 1}`;
const IP_LOGIN_BURST = `203.0.113.${RUN_BASE + 2}`;
const IP_ACCESS_DENIAL = `203.0.113.${RUN_BASE + 3}`;
const IP_HIGH_VOLUME = `203.0.113.${RUN_BASE + 4}`;
const IP_SHARED_ALERT = `203.0.113.${RUN_BASE + 5}`;

interface Fixture {
  ownerEmail: string;
  analystEmail: string;
  outsiderEmail: string;
  workspaceId: string;
  sourceId: string;
  ingestionKey: string;
}

let fixture: Fixture | null = null;

/** Seed the shared fixture once for the whole serial suite. */
async function ensureFixture(): Promise<Fixture> {
  if (fixture) return fixture;

  const owner = await registerUser(OWNER_EMAIL, PASSWORD, "E2E Owner");
  await registerUser(ANALYST_EMAIL, PASSWORD, "E2E Analyst");
  await registerUser(OUTSIDER_EMAIL, PASSWORD, "E2E Outsider");

  // Reuse the workspace when a previous run already created it.
  const workspaces = await apiRequest<{ id: string; name: string }[]>("/api/workspaces", {
    session: owner,
  });
  let workspaceId = workspaces.body.find((item) => item.name === WORKSPACE_NAME)?.id;
  if (!workspaceId) {
    const created = await apiRequest<{ id: string }>("/api/workspaces", {
      method: "POST",
      body: { name: WORKSPACE_NAME },
      session: owner,
    });
    expect(created.status).toBe(201);
    workspaceId = created.body.id;
  }

  const memberResponse = await apiRequest(`/api/workspaces/${workspaceId}/members`, {
    method: "POST",
    body: { email: ANALYST_EMAIL, role: "analyst" },
    session: owner,
  });
  // 409 means the member is already in the workspace from a previous run.
  expect([201, 409]).toContain(memberResponse.status);

  const sources = await apiRequest<{ id: string; label: string }[]>("/api/sources", {
    session: owner,
    workspaceId,
  });
  let sourceId = sources.body.find((item) => item.label === "E2E Demo API")?.id;
  let ingestionKey = "";
  if (sourceId) {
    // The raw key is only returned on creation or rotation.
    const rotated = await apiRequest<{ ingestion_key: string }>(
      `/api/sources/${sourceId}/rotate`,
      { method: "POST", session: owner, workspaceId },
    );
    expect(rotated.status).toBe(200);
    ingestionKey = rotated.body.ingestion_key;
  } else {
    const sourceResponse = await apiRequest<{ id: string; ingestion_key: string }>("/api/sources", {
      method: "POST",
      body: { label: "E2E Demo API" },
      session: owner,
      workspaceId,
    });
    expect(sourceResponse.status).toBe(201);
    sourceId = sourceResponse.body.id;
    ingestionKey = sourceResponse.body.ingestion_key;
  }

  fixture = {
    ownerEmail: OWNER_EMAIL,
    analystEmail: ANALYST_EMAIL,
    outsiderEmail: OUTSIDER_EMAIL,
    workspaceId,
    sourceId,
    ingestionKey,
  };
  return fixture;
}

async function signIn(page: Page, email: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("link", { name: "Overview" })).toBeVisible();
}

/** Open the event explorer with a wide time range. */
async function openEventExplorer(page: Page): Promise<void> {
  await page.getByRole("link", { name: "Events" }).click();
  await expect(page.getByRole("heading", { name: "Event explorer" })).toBeVisible();
  await page.getByLabel("From").fill("2000-01-01T00:00");
  await page.getByLabel("To").fill("2099-01-01T00:00");
}

test.describe.configure({ mode: "serial" });

test("registration, workspace and source setup", async ({ page }) => {
  const data = await ensureFixture();

  await signIn(page, data.ownerEmail);
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();

  // The source exists and the workspace is selected.
  await page.getByRole("link", { name: "Sources" }).click();
  await expect(page.getByRole("heading", { name: "Monitored API sources" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "E2E Demo API" })).toBeVisible();

  // The team page lists both members.
  await page.getByRole("link", { name: "Team" }).click();
  await expect(page.getByRole("heading", { name: "Team" })).toBeVisible();
  await expect(page.getByRole("cell", { name: data.analystEmail })).toBeVisible();
});

test("an ordinary ingested event appears in the event explorer", async ({ page }) => {
  const data = await ensureFixture();
  const status = await ingestEvent(data.ingestionKey, {
    event_id: newEventId(),
    event_type: "request",
    source_ip: IP_ORDINARY,
    route_template: "GET /api/products",
    method: "GET",
    status_code: 200,
    duration_ms: 17,
  });
  expect([200, 202]).toContain(status);

  await signIn(page, data.ownerEmail);
  await openEventExplorer(page);
  await page.getByRole("button", { name: "Apply filters" }).click();

  await expect(page.getByRole("cell", { name: IP_ORDINARY }).first()).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByRole("cell", { name: "GET /api/products" }).first()).toBeVisible();
});

test("event filters narrow the result set", async ({ page }) => {
  const data = await ensureFixture();
  await ingestEvent(data.ingestionKey, {
    event_id: newEventId(),
    event_type: "request",
    source_ip: IP_FILTERED,
    route_template: "GET /api/orders",
    method: "GET",
    status_code: 404,
  });

  await signIn(page, data.ownerEmail);
  await openEventExplorer(page);
  await page.getByLabel("Source IP").fill(IP_FILTERED);
  await page.getByRole("button", { name: "Apply filters" }).click();

  await expect(page.getByRole("cell", { name: IP_FILTERED }).first()).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByRole("cell", { name: IP_ORDINARY })).toHaveCount(0);

  // Resetting the filters brings the wider result set back.
  await page.getByRole("button", { name: "Reset filters" }).click();
  await page.getByLabel("From").fill("2000-01-01T00:00");
  await page.getByLabel("To").fill("2099-01-01T00:00");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.getByRole("cell", { name: IP_ORDINARY }).first()).toBeVisible({
    timeout: 30_000,
  });
});

test("the three detection rules raise alerts with evidence", async ({ page }) => {
  const data = await ensureFixture();

  // failed_login_burst: 5 explicit login failures from one IP.
  for (let index = 0; index < 5; index += 1) {
    const status = await ingestEvent(data.ingestionKey, {
      event_id: newEventId(),
      event_type: "login_failed",
      source_ip: IP_LOGIN_BURST,
      route_template: "POST /auth/login",
      method: "POST",
      status_code: 401,
    });
    expect([200, 202]).toContain(status);
  }

  // repeated_access_denial: 10 HTTP 403 responses from another IP.
  for (let index = 0; index < 10; index += 1) {
    const status = await ingestEvent(data.ingestionKey, {
      event_id: newEventId(),
      event_type: "request",
      source_ip: IP_ACCESS_DENIAL,
      route_template: "GET /api/admin",
      method: "GET",
      status_code: 403,
    });
    expect([200, 202]).toContain(status);
  }

  // high_request_volume: 101 request events from a third IP.
  for (let index = 0; index < 101; index += 1) {
    const status = await ingestEvent(data.ingestionKey, {
      event_id: newEventId(),
      event_type: "request",
      source_ip: IP_HIGH_VOLUME,
      route_template: "GET /api/products",
      method: "GET",
      status_code: 200,
    });
    expect([200, 202]).toContain(status);
  }

  await signIn(page, data.ownerEmail);
  await page.getByRole("link", { name: "Alerts" }).click();
  await expect(page.getByRole("heading", { name: "Alerts" })).toBeVisible();

  await expectAlertRow(page, "failed_login_burst");
  await expectAlertRow(page, "repeated_access_denial");
  await expectAlertRow(page, "high_request_volume");
});

test("two members investigate an alert together and the history persists", async ({ page, context }) => {
  const data = await ensureFixture();

  // Raise one alert that both members can open.
  for (let index = 0; index < 5; index += 1) {
    await ingestEvent(data.ingestionKey, {
      event_id: newEventId(),
      event_type: "login_failed",
      source_ip: IP_SHARED_ALERT,
      route_template: "POST /auth/login",
      method: "POST",
      status_code: 401,
    });
  }

  await signIn(page, data.ownerEmail);
  await page.getByRole("link", { name: "Alerts" }).click();
  await expectAlertRowText(page, IP_SHARED_ALERT, 90_000);
  const alertRow = page.getByRole("row").filter({ hasText: IP_SHARED_ALERT }).first();
  await expect(alertRow).toBeVisible({ timeout: 60_000 });
  await alertRow.getByRole("link").first().click();

  await expect(page.getByRole("heading", { name: "Why this fired" })).toBeVisible();
  // The evidence of the trigger is shown.
  await expect(page.getByRole("heading", { name: /^Evidence \(\d+\)$/ })).toBeVisible();
  await expect(page.getByRole("cell", { name: IP_SHARED_ALERT }).first()).toBeVisible();

  // The owner assigns the alert to the analyst.
  await page.getByLabel("Assign to").selectOption({ label: "E2E Analyst (analyst)" });
  // The assignee is shown in the alert facts, not only inside the dropdown.
  await expect(page.locator("dd", { hasText: "E2E Analyst" }).first()).toBeVisible({
    timeout: 30_000,
  });

  // A second member comments in a separate browser session.
  const analystContext = await context.browser()!.newContext();
  const analystPage = await analystContext.newPage();
  await signIn(analystPage, data.analystEmail);
  await analystPage.goto(page.url());
  await analystPage.getByLabel("Add a comment").fill("Checked the source logs, no breach.");
  await analystPage.getByRole("button", { name: "Post comment" }).click();
  await expect(analystPage.getByText("Checked the source logs, no breach.")).toBeVisible({
    timeout: 30_000,
  });

  // The owner reloads and sees the persisted comment and the history.
  await page.reload();
  await expect(page.getByText("Checked the source logs, no breach.")).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText("commented", { exact: false }).first()).toBeVisible();

  // The alert is moved to investigating and finally resolved.
  await page.getByRole("button", { name: "Move to investigating" }).click();
  await expect(page.getByText("status changed", { exact: false }).first()).toBeVisible({
    timeout: 30_000,
  });
  await page.getByRole("button", { name: "Move to resolved" }).click();
  await expect(page.getByText("Resolved", { exact: true }).first()).toBeVisible({ timeout: 30_000 });

  // A terminal alert no longer accepts status changes.
  await expect(page.getByText("This alert is in a terminal status")).toBeVisible();

  await analystContext.close();
});

test("a signed-in non-member cannot reach the workspace data", async ({ page }) => {
  const data = await ensureFixture();
  await signIn(page, data.outsiderEmail);

  // The outsider does not see the workspace in the selector.
  await expect(page.getByRole("option", { name: WORKSPACE_NAME })).toHaveCount(0);

  // A direct request for the workspace members is refused.
  const response = await page.request.get(`/api/workspaces/${data.workspaceId}/members`, {
    headers: { "X-Workspace-Id": data.workspaceId },
  });
  expect([403, 404]).toContain(response.status());
});
