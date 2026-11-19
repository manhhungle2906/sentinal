/**
 * The single HTTP client for the whole application.
 *
 * Every request goes through the same origin as the app, so the session cookie
 * is sent automatically. The CSRF token is read from its readable cookie and
 * echoed back in the X-CSRF-Token header for state-changing requests.
 */

const CSRF_COOKIE = "sentinel_csrf";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function readCsrfToken(): string | null {
  const match = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${CSRF_COOKIE}=`));
  return match ? decodeURIComponent(match.slice(CSRF_COOKIE.length + 1)) : null;
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  workspaceId?: string | null;
  signal?: AbortSignal | undefined;
}

const MUTATING_METHODS = new Set(["POST", "PATCH", "DELETE"]);

async function parseError(response: Response): Promise<string> {
  try {
    const data: unknown = await response.json();
    if (typeof data === "object" && data !== null && "detail" in data) {
      const detail = (data as { detail: unknown }).detail;
      if (typeof detail === "string") {
        return detail;
      }
      if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0] as { msg?: string };
        return first.msg ?? "The request was rejected.";
      }
    }
  } catch {
    // Fall through to the generic message.
  }
  return `Request failed with status ${response.status}.`;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };

  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (options.workspaceId) {
    headers["X-Workspace-Id"] = options.workspaceId;
  }
  if (MUTATING_METHODS.has(method)) {
    const csrf = readCsrfToken();
    if (csrf) {
      headers["X-CSRF-Token"] = csrf;
    }
  }

  let response: Response;
  try {
    const init: RequestInit = {
      method,
      headers,
      credentials: "same-origin",
    };
    if (options.body !== undefined) {
      init.body = JSON.stringify(options.body);
    }
    if (options.signal !== undefined) {
      init.signal = options.signal;
    }
    response = await fetch(path, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError(0, "The server could not be reached. Check your connection.");
  }

  if (!response.ok) {
    throw new ApiError(response.status, await parseError(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  if (!text) {
    return undefined as T;
  }
  return JSON.parse(text) as T;
}
