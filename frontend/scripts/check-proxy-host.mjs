import { createServer } from "vite";

/**
 * End-to-end check of the dev proxy against the real Core API.
 *
 * The script signs in through the Vite dev proxy, then performs an alert
 * assignment through the same proxy. The assignment endpoint is protected by
 * both the CSRF check and the same-origin check, so it reproduces the
 * reported `403 cross-origin request rejected` when the proxy rewrites the
 * Host header.
 *
 * A correct setup reaches the alert lookup and answers 404 (no such alert).
 * A broken setup answers 403 with `cross-origin request rejected`.
 */
const port = Number(process.env.PROXY_PORT ?? 5199);
const browserOrigin = `http://127.0.0.1:${port}`;
const coreTarget = process.env.CORE_TARGET ?? "http://127.0.0.1:8000";
const changeOrigin = process.env.PROXY_CHANGE_ORIGIN === "true";

const email = process.env.CHECK_EMAIL ?? "proxy-check@example.com";
const password = process.env.CHECK_PASSWORD ?? "proxy-check-password";

const vite = await createServer({
  configFile: "/app/vite.config.ts",
  optimizeDeps: { noDiscovery: true, include: [] },
  server: {
    host: "127.0.0.1",
    port,
    strictPort: true,
    proxy: {
      "/api": {
        target: coreTarget,
        ...(changeOrigin ? { changeOrigin: true } : {}),
      },
    },
  },
  logLevel: "error",
});
await vite.listen();

const jar = new Map();
function rememberCookies(response) {
  for (const raw of response.headers.getSetCookie?.() ?? []) {
    const [pair] = raw.split(";");
    const index = pair.indexOf("=");
    if (index > 0) {
      jar.set(pair.slice(0, index).trim(), pair.slice(index + 1).trim());
    }
  }
}
function cookieHeader() {
  return [...jar.entries()].map(([name, value]) => `${name}=${value}`).join("; ");
}

const register = await fetch(`${browserOrigin}/api/auth/register`, {
  method: "POST",
  headers: { Origin: browserOrigin, "Content-Type": "application/json" },
  body: JSON.stringify({ email, password, display_name: "Proxy Check" }),
});
rememberCookies(register);

const login = await fetch(`${browserOrigin}/api/auth/login`, {
  method: "POST",
  headers: { Origin: browserOrigin, "Content-Type": "application/json" },
  body: JSON.stringify({ email, password }),
});
rememberCookies(login);

const csrf = jar.get("sentinel_csrf");

const workspaces = await fetch(`${browserOrigin}/api/workspaces`, {
  headers: { Cookie: cookieHeader() },
});
const workspaceList = await workspaces.json();
let workspaceId = Array.isArray(workspaceList) ? workspaceList[0]?.id : undefined;

if (!workspaceId) {
  const created = await fetch(`${browserOrigin}/api/workspaces`, {
    method: "POST",
    headers: {
      Origin: browserOrigin,
      "Content-Type": "application/json",
      Cookie: cookieHeader(),
      "X-CSRF-Token": csrf ?? "",
    },
    body: JSON.stringify({ name: "Proxy Check" }),
  });
  const createdBody = await created.json();
  workspaceId = createdBody?.id;
}

const assignment = await fetch(
  `${browserOrigin}/api/alerts/00000000-0000-0000-0000-000000000000/assignee`,
  {
    method: "PATCH",
    headers: {
      Origin: browserOrigin,
      "Content-Type": "application/json",
      Cookie: cookieHeader(),
      "X-CSRF-Token": csrf ?? "",
      "X-Workspace-Id": workspaceId ?? "",
    },
    body: JSON.stringify({ assignee_id: null }),
  },
);
const body = await assignment.text();

console.log(
  JSON.stringify(
    {
      browserOrigin,
      changeOrigin,
      registerStatus: register.status,
      loginStatus: login.status,
      workspaceId,
      assignmentStatus: assignment.status,
      body: body.slice(0, 300),
      rejectedAsCrossOrigin: body.includes("cross-origin request rejected"),
    },
    null,
    2,
  ),
);

await vite.close();
if (body.includes("cross-origin request rejected")) {
  process.exitCode = 1;
}
