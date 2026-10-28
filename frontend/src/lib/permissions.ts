import type { Session } from "@/features/auth/session";

export const CAPABILITIES = {
  RESET_DATA: "data.reset",
  MANAGE_USERS: "users.manage",
  MANAGE_PRIVILEGES: "privileges.manage",
  CREATE_PROJECTS: "projects.create",
  EDIT_PROJECTS: "projects.edit",
  VALIDATE_PROJECT_CLOSURE: "projects.validate_closure",
  ANNOTATE_OWN_PROJECTS: "projects.annotate_own",
  CREATE_TIMESHEETS: "timesheets.create",
  EDIT_TIMESHEETS: "timesheets.edit",
  EDIT_WALLET: "wallet.edit",
  MANAGE_CANONE: "canone.manage",
  ADJUST_ACCOUNTING: "accounting.adjust",
  UPLOAD_IMPORTS: "imports.upload",
  APPLY_IMPORTS: "imports.apply",
  EXPORT_DATA: "exports.run",
  RESOLVE_ANOMALIES: "anomalies.resolve",
} as const;

export type Capability = (typeof CAPABILITIES)[keyof typeof CAPABILITIES];

/**
 * La GUI usa le capability di sessione solo per visibilità/abilitazione. Durante il rollout,
 * quando il campo non è ancora presente, preserva i controlli legacy su ruoli e flag.
 */
export function hasCapability(
  session: Session | null,
  capability: Capability,
  legacyFallback: (session: Session) => boolean = () => false,
): boolean {
  if (!session) return false;
  if (Array.isArray(session.capabilities)) return session.capabilities.includes(capability);
  return legacyFallback(session);
}

export function canManageCanone(session: Session | null): boolean {
  return hasCapability(
    session,
    CAPABILITIES.MANAGE_CANONE,
    (legacy) => legacy.is_admin || legacy.roles.includes("fornitore"),
  );
}

export function canWriteLedger(session: Session | null): boolean {
  return hasCapability(session, CAPABILITIES.ADJUST_ACCOUNTING, (legacy) => legacy.can_write);
}

export function canCreateTimesheets(session: Session | null): boolean {
  return hasCapability(
    session,
    CAPABILITIES.CREATE_TIMESHEETS,
    (legacy) => legacy.can_write || legacy.roles.includes("fornitore"),
  );
}

export function canEditTimesheets(session: Session | null): boolean {
  return hasCapability(session, CAPABILITIES.EDIT_TIMESHEETS, (legacy) => legacy.is_admin);
}

export function canAdminister(session: Session | null): boolean {
  return hasCapability(session, CAPABILITIES.MANAGE_PRIVILEGES, (legacy) => legacy.is_admin);
}

export function canResetData(session: Session | null): boolean {
  return hasCapability(session, CAPABILITIES.RESET_DATA, (legacy) => legacy.is_admin);
}

export function canCreateProjects(session: Session | null): boolean {
  return hasCapability(
    session,
    CAPABILITIES.CREATE_PROJECTS,
    (legacy) => legacy.can_write || legacy.roles.includes("fornitore"),
  );
}

export function canEditProjects(session: Session | null): boolean {
  return hasCapability(
    session,
    CAPABILITIES.EDIT_PROJECTS,
    (legacy) => legacy.is_admin || Boolean(legacy.roles?.includes("responsabile_bmed")),
  );
}

export function canValidateProjectClosure(session: Session | null): boolean {
  return hasCapability(session, CAPABILITIES.VALIDATE_PROJECT_CLOSURE, (legacy) =>
    Boolean(legacy.is_admin || legacy.roles?.includes("fornitore")),
  );
}

export function canAnnotateOwnProjects(session: Session | null): boolean {
  return hasCapability(session, CAPABILITIES.ANNOTATE_OWN_PROJECTS, (legacy) =>
    Boolean(legacy.roles?.includes("referente_bmed")),
  );
}

export function canUploadPpmDryRun(session: Session | null): boolean {
  return hasCapability(
    session,
    CAPABILITIES.UPLOAD_IMPORTS,
    (legacy) => legacy.roles.includes("fornitore") || legacy.can_write,
  );
}

export function canEditWallet(session: Session | null): boolean {
  return hasCapability(
    session,
    CAPABILITIES.EDIT_WALLET,
    (legacy) =>
      legacy.is_admin ||
      Boolean(legacy.roles?.some((role) => ["responsabile_bmed", "fornitore"].includes(role))),
  );
}

export function canAdjustAccounting(session: Session | null): boolean {
  return hasCapability(
    session,
    CAPABILITIES.ADJUST_ACCOUNTING,
    (legacy) => legacy.is_admin || Boolean(legacy.roles?.includes("responsabile_bmed")),
  );
}
