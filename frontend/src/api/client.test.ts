import { describe, expect, it } from "vitest";
import { ApiError, readCsrfToken } from "./client";

describe("readCsrfToken", () => {
  it("returns null when the cookie is absent", () => {
    document.cookie = "sentinel_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    expect(readCsrfToken()).toBeNull();
  });

  it("reads the CSRF cookie value", () => {
    document.cookie = "sentinel_csrf=test-token-value";
    expect(readCsrfToken()).toBe("test-token-value");
  });
});

describe("ApiError", () => {
  it("keeps the HTTP status", () => {
    const error = new ApiError(403, "forbidden");
    expect(error.status).toBe(403);
    expect(error.message).toBe("forbidden");
    expect(error).toBeInstanceOf(Error);
  });
});
