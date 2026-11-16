import { describe, expect, it } from "vitest";
import { formatSize, priorityLabel, statusLabel } from "./format.js";

describe("format", () => {
  it("traduit les statuts connus", () => {
    expect(statusLabel("in_progress")).toBe("En cours");
  });

  it("garde la valeur brute pour un statut inconnu", () => {
    expect(statusLabel("autre")).toBe("autre");
  });

  it("traduit les priorités", () => {
    expect(priorityLabel("urgent")).toBe("Urgente");
  });

  it("formate les tailles de fichiers", () => {
    expect(formatSize(512)).toBe("512 o");
    expect(formatSize(2048)).toBe("2.0 Ko");
    expect(formatSize(3 * 1024 * 1024)).toBe("3.0 Mo");
  });
});
