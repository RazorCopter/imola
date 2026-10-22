import { describe, expect, it } from "vitest";

import type { Session } from "@/features/auth/session";
import { canAdminister, canUploadPpmDryRun, canWriteLedger } from "@/lib/permissions";

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

  it("nega tutte le capability in assenza di sessione", () => {
    expect(canWriteLedger(null)).toBe(false);
    expect(canAdminister(null)).toBe(false);
    expect(canUploadPpmDryRun(null)).toBe(false);
  });
});
