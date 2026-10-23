import { describe, expect, it } from "vitest";

import type { Session } from "@/features/auth/session";
import {
  CAPABILITIES,
  canAdminister,
  canCreateProjects,
  canUploadPpmDryRun,
  canWriteLedger,
} from "@/lib/permissions";

function session(overrides: Partial<Session>): Session {
  return {
    username: "utente-test",
    full_name: "Utente Test",
    email: "utente@example.test",
    roles: [],
    is_admin: false,
    can_write: false,
    ...overrides,
  };
}

describe("permission UI derivate dalla sessione", () => {
  it.each([
    ["admin", session({ roles: ["admin"], is_admin: true, can_write: true }), true, true],
    ["responsabile", session({ roles: ["responsabile_bmed"], can_write: true }), true, false],
    ["referente", session({ roles: ["referente_bmed"] }), false, false],
    ["fornitore", session({ roles: ["fornitore"] }), false, false],
  ])("allinea scrittura ledger e amministrazione per %s", (_role, value, write, admin) => {
    expect(canWriteLedger(value)).toBe(write);
    expect(canAdminister(value)).toBe(admin);
  });

  it("consente il dry-run PPM al fornitore e ai writer, non al referente", () => {
    expect(canUploadPpmDryRun(session({ roles: ["fornitore"] }))).toBe(true);
    expect(canUploadPpmDryRun(session({ roles: ["responsabile_bmed"], can_write: true }))).toBe(
      true,
    );
    expect(canUploadPpmDryRun(session({ roles: ["referente_bmed"] }))).toBe(false);
  });

  it("usa le capability quando presenti, anche se i flag legacy differiscono", () => {
    const supplier = session({
      roles: ["fornitore"],
      capabilities: [CAPABILITIES.CREATE_PROJECTS, CAPABILITIES.UPLOAD_IMPORTS],
      can_write: true,
      is_admin: true,
    });

    expect(canCreateProjects(supplier)).toBe(true);
    expect(canUploadPpmDryRun(supplier)).toBe(true);
    expect(canWriteLedger(supplier)).toBe(false);
    expect(canAdminister(supplier)).toBe(false);
  });

  it("mantiene il fallback legacy se capabilities è assente", () => {
    expect(canCreateProjects(session({ can_write: true }))).toBe(true);
    expect(canUploadPpmDryRun(session({ roles: ["fornitore"] }))).toBe(true);
  });

  it("nega tutte le capability in assenza di sessione", () => {
    expect(canWriteLedger(null)).toBe(false);
    expect(canAdminister(null)).toBe(false);
    expect(canUploadPpmDryRun(null)).toBe(false);
    expect(canCreateProjects(null)).toBe(false);
  });
});
