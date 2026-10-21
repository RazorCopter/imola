import { cn } from "@/lib/utils";

type StatusDomain = "timesheet" | "billing" | "offer" | "generic";
type Tone = "neutral" | "ok" | "warn" | "danger";

const LABELS: Record<string, string> = {
  NON_AVVIATO: "Non avviato",
  ATTIVO: "Attivo",
  CHIUSO: "Chiuso",
  DA_VERIFICARE: "Da verificare",
  DA_FATTURARE: "Da fatturare",
  PARZIALE: "Parziale",
  TOTALE: "Totale",
  NON_FATTURABILE: "Non fatturabile",
  INVIATA: "Inviata",
  ACCETTATA: "Accettata",
  SCADUTA: "Scaduta",
  NON_ACCETTATA: "Non accettata",
  APERTA: "Aperta",
  RISOLTA: "Risolta",
  ACCETTATA_CON_DEROGA: "Accettata con deroga",
};

const DOMAIN_LABELS: Record<StatusDomain, string> = {
  timesheet: "Consuntivazione",
  billing: "Fatturazione",
  offer: "Offerta",
  generic: "Stato",
};

function statusTone(status: string): Tone {
  if (["CHIUSO", "TOTALE", "ACCETTATA", "RISOLTA"].includes(status)) return "ok";
  if (["DA_VERIFICARE", "PARZIALE", "INVIATA", "APERTA"].includes(status)) return "warn";
  if (["SCADUTA", "NON_ACCETTATA"].includes(status)) return "danger";
  return "neutral";
}

export function StatusBadge({
  status,
  domain = "generic",
}: {
  status: string;
  domain?: StatusDomain;
}) {
  const tone = statusTone(status);
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
        tone === "ok" && "border-ok/30 bg-ok-subtle text-ok",
        tone === "warn" && "border-warn/30 bg-warn-subtle text-warn",
        tone === "danger" && "border-danger/30 bg-danger-subtle text-danger",
        tone === "neutral" && "border-border bg-muted text-muted-foreground",
      )}
      title={`${DOMAIN_LABELS[domain]}: ${LABELS[status] ?? status}`}
    >
      <span className="sr-only">{DOMAIN_LABELS[domain]}: </span>
      {LABELS[status] ?? status.replaceAll("_", " ").toLocaleLowerCase("it")}
    </span>
  );
}
