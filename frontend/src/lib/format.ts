/**
 * Formattazione dei dati contabili.
 *
 * REGOLA: le giornate sono stringhe e restano stringhe. Arrivano dall'API come tali
 * (`api/renderers.py` serializza ogni Decimal come stringa) perché in JavaScript ogni
 * numero è un float a doppia precisione: `Number("0.1") + Number("0.2")` fa
 * 0.30000000000000004, e su dati contabili non è accettabile.
 *
 * Di conseguenza, nel client non si fa **nessun calcolo** sulle giornate: niente somme,
 * sottrazioni, delta o percentuali. Tutti i totali — residui, disponibile wallet, delta del
 * canone, scostamenti di riconciliazione — arrivano già calcolati dalle viste di dominio del
 * backend, dove vivono in Decimal a 4 cifre. Qui si converte a numero solo dentro i
 * formattatori, nell'ultimo passaggio prima dello schermo, e solo per arrotondare a due
 * decimali e mettere i separatori italiani.
 *
 * Se serve un numero nuovo, si aggiunge al backend (`backend/domain/`) e si espone in API:
 * non si calcola qui. Vedi la voce D-15 in docs/DECISIONI_APERTE.md.
 */

export type DaysValue = string | number | null | undefined;

// useGrouping true (= always): in it-IT il default sopprime il punto nei numeri a 4 cifre
// (1234 invece di 1.234), mentre il formato richiesto è sempre 1.234,56 gg.
const daysFormatter = new Intl.NumberFormat("it-IT", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  useGrouping: true,
});

const integerFormatter = new Intl.NumberFormat("it-IT", { useGrouping: true });

export function parseDays(value: DaysValue): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = typeof value === "number" ? value : Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** 1234.56 -> "1.234,56 gg" */
export function formatDays(value: DaysValue, { suffix = true } = {}): string {
  const parsed = parseDays(value);
  if (parsed === null) return "–";
  const text = daysFormatter.format(parsed);
  return suffix ? `${text} gg` : text;
}

/** Variante compatta per le celle di tabella, senza unità ripetuta su ogni riga. */
export function formatDaysCell(value: DaysValue): string {
  return formatDays(value, { suffix: false });
}

export function formatCount(value: number | null | undefined): string {
  return value === null || value === undefined ? "–" : integerFormatter.format(value);
}

export function formatPercent(value: DaysValue, digits = 1): string {
  const parsed = parseDays(value);
  if (parsed === null) return "–";
  return `${new Intl.NumberFormat("it-IT", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    useGrouping: true,
  }).format(parsed)}%`;
}

/** Delta con segno esplicito: il segno è informazione, non decorazione. */
export function formatDelta(value: DaysValue): string {
  const parsed = parseDays(value);
  if (parsed === null) return "–";
  const sign = parsed > 0 ? "+" : "";
  return `${sign}${formatDays(parsed)}`;
}

export function deltaTone(value: DaysValue): "ok" | "warn" | "neutral" {
  const parsed = parseDays(value);
  if (parsed === null) return "neutral";
  if (parsed >= 0) return "ok";
  return "warn";
}
