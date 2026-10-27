export const RECONCILIATION_OUTCOMES = ["OK", "KO", "ASSENTE_IN_PPM"] as const;

export type ReconciliationOutcome = (typeof RECONCILIATION_OUTCOMES)[number];
export type ReconciliationOutcomeTone = "ok" | "danger" | "warn" | "neutral";

export interface ReconciliationOutcomePresentation {
  label: string;
  tone: ReconciliationOutcomeTone;
  known: boolean;
}

const OUTCOME_PRESENTATIONS: Record<ReconciliationOutcome, ReconciliationOutcomePresentation> = {
  OK: { label: "Valido", tone: "ok", known: true },
  KO: { label: "DISCREPANZA", tone: "danger", known: true },
  ASSENTE_IN_PPM: { label: "Assente PPM", tone: "warn", known: true },
};

/**
 * Traduce il contratto backend in una presentazione semantica.
 * Un valore futuro o non valido resta visibile e neutro, senza essere confuso
 * con uno degli esiti riconosciuti.
 */
export function getReconciliationOutcomePresentation(
  outcome: string,
): ReconciliationOutcomePresentation {
  if (Object.prototype.hasOwnProperty.call(OUTCOME_PRESENTATIONS, outcome)) {
    return OUTCOME_PRESENTATIONS[outcome as ReconciliationOutcome];
  }
  return {
    label: outcome ? `Esito sconosciuto: ${outcome}` : "Esito sconosciuto",
    tone: "neutral",
    known: false,
  };
}
