import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * The Core API rejects a state-changing request whose Host header does not
 * match the browser Origin with `403 cross-origin request rejected`.
 *
 * Vite rewrites the Host header to the upstream host when `changeOrigin` is
 * true, which makes every assignment, comment and status change fail behind
 * the dev server. The dev proxy must therefore keep the browser Host.
 *
 * The configuration is read as text because the file sits outside the `src`
 * tree that Vitest transforms, and because the check must look at the value
 * that Vite actually receives.
 */
const configPath = resolve(process.cwd(), "vite.config.ts");
const configSource = readFileSync(configPath, "utf8");

describe("the dev server proxy", () => {
  it("proxies the API and the ingestion routes", () => {
    expect(configSource).toContain('"/api"');
    expect(configSource).toContain('"/ingest"');
  });

  it("keeps the browser Host header so the same-origin check passes", () => {
    const origins = [...configSource.matchAll(/changeOrigin:\s*(true|false)/g)].map(
      (match) => match[1],
    );

    expect(origins.length).toBeGreaterThan(0);
    expect(origins).not.toContain("true");
    for (const origin of origins) {
      expect(origin).toBe("false");
    }
  });
});
