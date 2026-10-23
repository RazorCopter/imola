import type { Session } from "@/features/auth/session";

export const CAPABILITIES = {
  RESET_DATA: "data.reset",
  MANAGE_USERS: "users.manage",
  MANAGE_PRIVILEGES: "privileges.manage",
  CREATE_PROJECTS: "projects.create",
  EDIT_PROJECTS: "projects.edit",
  ANNOTATE_OWN_PROJECTS: "projects.annotate_own",
  CREATE_TIMESHEETS: "timesheets.create",
  EDIT_WALLET: "wallet.edit",
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
  if (session.capabilities !== undefined) return session.capabilities.includes(capability);
  return legacyFallback(session);
}

export function canWriteLedger(session: Session | null): boolean {
  return hasCapability(session, CAPABILITIES.ADJUST_ACCOUNTING, (legacy) => legacy.can_write);
}

export function canAdminister(session: Session | null): boolean {
  return hasCapability(session, CAPABILITIES.MANAGE_PRIVILEGES, (legacy) => legacy.is_admin);
}

export function canCreateProjects(session: Session | null): boolean {
  return hasCapability(session, CAPABILITIES.CREATE_PROJECTS, (legacy) => legacy.can_write);
}

export function canUploadPpmDryRun(session: Session | null): boolean {
  return hasCapability(
    session,
    CAPABILITIES.UPLOAD_IMPORTS,
    (legacy) => legacy.roles.includes("fornitore") || legacy.can_write,
  );
}
