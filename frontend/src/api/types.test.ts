import { describe, expect, it } from "vitest";
import { isOpen, isTerminal, severityLabel, statusLabel } from "./types";

describe("alert status helpers", () => {
  it("treats new and investigating as open", () => {
    expect(isOpen("new")).toBe(true);
    expect(isOpen("investigating")).toBe(true);
    expect(isOpen("resolved")).toBe(false);
    expect(isOpen("false_positive")).toBe(false);
  });

  it("treats resolved and false positive as terminal", () => {
    expect(isTerminal("resolved")).toBe(true);
    expect(isTerminal("false_positive")).toBe(true);
    expect(isTerminal("new")).toBe(false);
    expect(isTerminal("investigating")).toBe(false);
  });

  it("renders readable labels", () => {
    expect(statusLabel("new")).toBe("New");
    expect(statusLabel("investigating")).toBe("Investigating");
    expect(statusLabel("resolved")).toBe("Resolved");
    expect(statusLabel("false_positive")).toBe("False positive");
    expect(severityLabel("critical")).toBe("Critical");
  });
});
