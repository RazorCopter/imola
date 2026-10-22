import type { Session } from "@/features/auth/session";

/**
 * La GUI deriva le capability dal payload di sessione; l'API resta la fonte di sicurezza.
 * Queste funzioni governano soltanto visibilità e abilitazione delle azioni.
 */
export function canWriteLedger(session: Session | null): boolean {
  return session?.can_write === true;
}

export function canAdminister(session: Session | null): boolean {
  return session?.is_admin === true;
}

export function canUploadPpmDryRun(session: Session | null): boolean {
  return session?.roles.includes("fornitore") === true || canWriteLedger(session);
}
