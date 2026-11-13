/**
 * Importazione settimanale dei consuntivi dall'estratto operativo.
 *
 * Flusso guidato ad alta leggibilità:
 * 1. Caricamento drag-and-drop con ispezione del file Excel.
 * 2. Analisi e cruscotto KPI per foglio (Progetti, Wallet, Organico allargato).
 * 3. Console di integrità con filtro errori/avvisi e copia rapida.
 * 4. Riconciliazione inline con suggerimenti intelligenti a 1-click.
 * 5. Tabella interattiva di anteprima con ricerca e filtri di stato.
 * 6. Stazione esecutiva di validazione e conferma nel ledger.
 * 7. Storico verificabile delle importazioni passate.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Copy,
  FileSpreadsheet,
  FolderGit2,
  History,
  Info,
  Link2,
  RotateCcw,
  Search,
  Sparkles,
  Upload,
  UploadCloud,
  Users,
  Wallet,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";

import { Button, Input, Select } from "@/components/Controls";
import { KpiCard } from "@/components/KpiCard";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/UiState";
import { api, ApiError } from "@/lib/api";
import { formatDays } from "@/lib/format";
import { cn } from "@/lib/utils";

const SEZIONI = [
  { id: "PROGETTI", label: "Progetti", icon: FolderGit2 },
  { id: "WALLET", label: "Wallet", icon: Wallet },
  { id: "ORGANICO", label: "Organico allargato", icon: Users },
] as const;

type SezioneId = (typeof SEZIONI)[number]["id"];

interface Problema {
  livello: "ERROR" | "WARNING";
  foglio: string;
  cella: string;
  riga: number | null;
  messaggio: string;
}

interface Riepilogo {
  sezione: SezioneId;
  etichetta: string;
  righe_lette: number;
  righe_importabili: number;
  righe_da_associare: number;
  righe_in_errore: number;
  righe_di_totale_escluse: number;
  giornate: string;
}

interface Candidato {
  id: string;
  etichetta: string;
  dettaglio: string;
  somiglianza: number;
}

interface DaAssociare {
  chiave: string;
  tipo: "PROGETTO" | "WALLET_ALLOCATION" | "CANONE_SUBACTIVITY" | "COLLABORATORE";
  tipo_etichetta: string;
  sezione: SezioneId;
  valore: string;
  anno: number | null;
  semestre: string;
  righe: string[];
  suggerito: string | null;
  candidati: Candidato[];
}

interface Riga {
  id: string;
  sezione: SezioneId;
  foglio: string;
  riga_excel: number;
  destinazione_excel: string;
  destinazione_risolta: string | null;
  collaboratore_excel: string;
  utente: string | null;
  data: string;
  giornate: string;
  descrizione: string;
  stato: "PRONTA" | "DA_ASSOCIARE" | "ERRORE";
  motivazione: string;
  consuntivo: string | null;
}

interface Batch {
  id: string;
  file: string;
  stato: string;
  stato_etichetta: string;
  impronta: string;
  creato_il: string;
  operatore: string | null;
  applicato_da: string | null;
  applicato_il: string | null;
  errore: string;
  confermabile: boolean;
  errori_bloccanti?: string[];
  report: {
    sezioni?: Riepilogo[];
    problemi?: Problema[];
    collaboratori_censiti?: string[];
    da_associare?: DaAssociare[];
    totale_righe?: number;
    totale_giornate?: string;
    applicato?: { movimenti: number; giornate: string; operatore: string; istante: string };
  } | null;
  righe?: Riga[];
}

const STATO_RIGA_CONFIG: Record<
  Riga["stato"],
  { label: string; badgeClass: string; dotClass: string }
> = {
  PRONTA: {
    label: "Pronta",
    badgeClass: "border-ok/30 bg-ok-subtle text-ok",
    dotClass: "bg-ok",
  },
  DA_ASSOCIARE: {
    label: "Da associare",
    badgeClass: "border-warn/30 bg-warn-subtle text-warn",
    dotClass: "bg-warn",
  },
  ERRORE: {
    label: "Errore",
    badgeClass: "border-danger/30 bg-danger-subtle text-danger",
    dotClass: "bg-danger",
  },
};

const TIPO_ASSOCIAZIONE_BADGE: Record<DaAssociare["tipo"], string> = {
  PROGETTO: "border-sky-500/30 bg-sky-500/10 text-sky-400",
  WALLET_ALLOCATION: "border-purple-500/30 bg-purple-500/10 text-purple-400",
  CANONE_SUBACTIVITY: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  COLLABORATORE: "border-amber-500/30 bg-amber-500/10 text-amber-400",
};

function formatData(iso: string): string {
  const [anno, mese, giorno] = iso.split("-");
  return giorno ? `${giorno}/${mese}/${anno}` : iso;
}

function formatIstante(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("it-IT");
}

function formatDimensione(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * Indicatore visuale a step del workflow di importazione.
 */
function WorkflowStepper({
  batch,
  daAssociareCount,
  erroriCount,
}: {
  batch: Batch | null;
  daAssociareCount: number;
  erroriCount: number;
}) {
  const applicato = batch?.stato === "APPLIED";
  const hasAnalysis = Boolean(batch);

  const steps = [
    {
      id: "caricamento",
      label: "1. Caricamento",
      desc: batch?.file ? batch.file : "File .xlsx",
      state: hasAnalysis ? "done" : "current",
    },
    {
      id: "analisi",
      label: "2. Analisi & Controlli",
      desc: hasAnalysis
        ? erroriCount > 0
          ? `${erroriCount} anomalie`
          : "Integrità verificata"
        : "In attesa file",
      state: !hasAnalysis
        ? "upcoming"
        : erroriCount > 0
          ? "warning"
          : "done",
    },
    {
      id: "riconciliazione",
      label: "3. Riconciliazione",
      desc: !hasAnalysis
        ? "Da verificare"
        : daAssociareCount > 0
          ? `${daAssociareCount} da associare`
          : "Completata",
      state: !hasAnalysis
        ? "upcoming"
        : daAssociareCount > 0
          ? "action_required"
          : "done",
    },
    {
      id: "anteprima",
      label: "4. Anteprima Dettaglio",
      desc: hasAnalysis ? `${batch?.righe?.length ?? 0} righe` : "In attesa",
      state: hasAnalysis ? (applicato ? "done" : "current") : "upcoming",
    },
    {
      id: "conferma",
      label: "5. Ledger Finale",
      desc: applicato
        ? "Applicato con successo"
        : batch?.confermabile
          ? "Pronto per l'applicazione"
          : "Bloccato",
      state: applicato ? "done" : batch?.confermabile ? "ready" : "upcoming",
    },
  ];

  return (
    <nav
      aria-label="Avanzamento del processo di importazione"
      className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5"
    >
      {steps.map((s) => {
        const isDone = s.state === "done";
        const isAction = s.state === "action_required";
        const isWarning = s.state === "warning";
        const isReady = s.state === "ready";
        const isCurrent = s.state === "current";

        return (
          <div
            key={s.id}
            className={cn(
              "flex flex-col justify-between rounded-xl border p-3.5 transition-all",
              isDone && "border-ok/30 bg-ok-subtle/30",
              isAction && "border-warn/50 bg-warn-subtle/40 shadow-sm",
              isWarning && "border-danger/30 bg-danger-subtle/30",
              isReady && "border-accent/50 bg-accent-subtle/50",
              isCurrent && "border-border bg-card shadow-subtle",
              s.state === "upcoming" && "border-border/50 bg-muted/30 opacity-60",
            )}
          >
            <div className="flex items-center justify-between gap-1.5">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {s.label}
              </span>
              {isDone && <CheckCircle2 className="size-4 shrink-0 text-ok" />}
              {isAction && <AlertTriangle className="size-4 shrink-0 text-warn animate-pulse" />}
              {isWarning && <AlertCircle className="size-4 shrink-0 text-danger" />}
              {isReady && <Sparkles className="size-4 shrink-0 text-accent" />}
            </div>
            <p className="mt-1 truncate text-xs font-medium text-foreground">{s.desc}</p>
          </div>
        );
      })}
    </nav>
  );
}

/**
 * Sezione Riconciliazione Inline: permette di associare codici o testi mancanti
 * memorizzandoli nel registro per le importazioni future.
 */
function SezioneRiconciliazioneInline({
  batch,
  gruppi,
  onAggiornato,
}: {
  batch: Batch;
  gruppi: DaAssociare[];
  onAggiornato: (nuovo: Batch) => void;
}) {
  const client = useQueryClient();
  const [scelte, setScelte] = useState<Record<string, string>>({});
  const [filtri, setFiltri] = useState<Record<string, string>>({});
  const [errore, setErrore] = useState<string | null>(null);

  useEffect(() => {
    setScelte(
      Object.fromEntries(
        gruppi.filter((g) => g.suggerito).map((g) => [g.chiave, g.suggerito as string]),
      ),
    );
    setFiltri({});
    setErrore(null);
  }, [batch.id, gruppi]);

  const salva = useMutation({
    mutationFn: async (associazioni: unknown[]) =>
      api.patch<Batch>(`/imports/operational/${batch.id}/mappings`, { associazioni }),
    onSuccess: (dati) => {
      setErrore(null);
      onAggiornato(dati);
      void client.invalidateQueries({ queryKey: ["associazioni"] });
    },
    onError: (err) =>
      setErrore(
        err instanceof ApiError ? err.message : "Salvataggio delle associazioni non riuscito.",
      ),
  });

  const daInviare = gruppi
    .filter((g) => scelte[g.chiave])
    .map((g) => ({
      tipo: g.tipo,
      valore: g.valore,
      destinazione: scelte[g.chiave],
      anno: g.anno,
      semestre: g.semestre,
    }));

  const completate = daInviare.length;
  const totale = gruppi.length;
  const percentuale = Math.round((completate / totale) * 100);

  return (
    <section className="rounded-xl border border-warn/40 bg-card p-5 shadow-subtle ring-1 ring-warn/20">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex size-7 items-center justify-center rounded-lg bg-warn/15 text-warn">
              <Link2 className="size-4" />
            </span>
            <h2 className="text-base font-semibold tracking-tight">
              3. Riconciliazione Voci Excel Mancanti
            </h2>
            <span className="rounded-full border border-warn/30 bg-warn-subtle px-2.5 py-0.5 text-xs font-semibold text-warn">
              {totale} {totale === 1 ? "voce" : "voci"} da completare
            </span>
          </div>
          <p className="mt-1.5 max-w-2xl text-xs text-muted-foreground">
            I valori rilevati nell'Excel non corrispondono a voci attualmente censite.
            Assegna la corretta destinazione: l'associazione verrà memorizzata nel registro e
            applicata in automatico a tutte le importazioni successive.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="text-xs font-medium text-muted-foreground">Progresso risoluzione</p>
            <p className="text-sm font-semibold tabular-nums text-foreground">
              {completate} di {totale} ({percentuale}%)
            </p>
          </div>
          <div className="h-2 w-24 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full bg-warn transition-all duration-300"
              style={{ width: `${percentuale}%` }}
            />
          </div>
        </div>
      </div>

      <ul className="mt-4 divide-y divide-border/60">
        {gruppi.map((g) => {
          const filtro = (filtri[g.chiave] ?? "").trim().toLowerCase();
          const candidati = filtro
            ? g.candidati.filter((c) =>
                `${c.etichetta} ${c.dettaglio}`.toLowerCase().includes(filtro),
              )
            : g.candidati;
          const contesto = g.semestre || (g.anno ? String(g.anno) : "");
          const scelto = scelte[g.chiave] ?? "";
          const candidatoSuggerito = g.suggerito
            ? g.candidati.find((c) => c.id === g.suggerito)
            : null;

          return (
            <li key={g.chiave} className="py-4 first:pt-2 last:pb-2">
              <div className="grid gap-3 lg:grid-cols-[minmax(0,1.2fr)_auto_minmax(0,2fr)] lg:items-center">
                {/* Voce rilevata nell'Excel */}
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={cn(
                        "rounded-md border px-2 py-0.5 text-xs font-semibold uppercase tracking-wider",
                        TIPO_ASSOCIAZIONE_BADGE[g.tipo] || "border-border bg-muted",
                      )}
                    >
                      {g.tipo_etichetta}
                    </span>
                    {contesto && (
                      <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                        {contesto}
                      </span>
                    )}
                    <span className="text-xs text-muted-foreground">
                      · {g.righe.length} {g.righe.length === 1 ? "riga" : "righe"} ({g.righe.slice(0, 4).join(", ")}
                      {g.righe.length > 4 ? "…" : ""})
                    </span>
                  </div>
                  <div className="flex items-center gap-2 pt-0.5">
                    <code className="rounded bg-muted/80 px-2 py-1 font-mono text-xs font-bold text-foreground">
                      {g.valore || "(vuoto)"}
                    </code>
                  </div>
                </div>

                {/* Freccia direzionale */}
                <div className="hidden lg:flex lg:justify-center">
                  <ArrowRight className="size-4 text-muted-foreground" />
                </div>

                {/* Scelta destinazione */}
                <div>
                  {g.candidati.length === 0 ? (
                    <div className="flex items-center gap-2 rounded-lg border border-danger/30 bg-danger-subtle p-2.5 text-xs text-danger">
                      <AlertCircle className="size-4 shrink-0" />
                      <span>
                        Nessuna voce censita nel sistema a cui associare questo valore. Creala
                        prima nell'apposita sezione, poi riesegui l'analisi del file.
                      </span>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {candidatoSuggerito && (
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-[11px] text-muted-foreground">Suggerimento:</span>
                          {scelto === g.suggerito ? (
                            <span className="inline-flex items-center gap-1.5 rounded-full border border-ok/40 bg-ok-subtle px-2.5 py-0.5 text-xs font-medium text-ok">
                              <Sparkles className="size-3" />
                              Suggerito: "{candidatoSuggerito.etichetta}" (preselezionato)
                            </span>
                          ) : (
                            <button
                              type="button"
                              onClick={() =>
                                setScelte((p) => ({ ...p, [g.chiave]: g.suggerito as string }))
                              }
                              className="inline-flex items-center gap-1.5 rounded-full border border-accent/40 bg-accent-subtle px-2.5 py-0.5 text-xs font-medium text-accent hover:bg-accent/20 transition-colors"
                            >
                              <Sparkles className="size-3" />
                              Usa "{candidatoSuggerito.etichetta}"
                            </button>
                          )}
                        </div>
                      )}

                      <div className="grid gap-2 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)]">
                        <Input
                          type="search"
                          placeholder="Filtra le opzioni…"
                          value={filtri[g.chiave] ?? ""}
                          aria-label={`Filtra le destinazioni per ${g.valore}`}
                          onChange={(e) =>
                            setFiltri((p) => ({ ...p, [g.chiave]: e.target.value }))
                          }
                          className="text-xs"
                        />
                        <Select
                          value={scelto}
                          aria-label={`Destinazione per ${g.valore}`}
                          onChange={(e) =>
                            setScelte((p) => ({ ...p, [g.chiave]: e.target.value }))
                          }
                          className={cn(
                            "text-xs font-medium",
                            scelto ? "border-ok/40 text-foreground" : "text-muted-foreground",
                          )}
                        >
                          <option value="">Seleziona la destinazione corretta…</option>
                          {candidati.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.etichetta}
                              {c.dettaglio ? ` — ${c.dettaglio}` : ""}
                              {c.id === g.suggerito ? "  (suggerito)" : ""}
                            </option>
                          ))}
                        </Select>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ul>

      {errore && (
        <div className="mt-4 rounded-lg border border-danger/30 bg-danger-subtle p-3 text-sm text-danger">
          {errore}
        </div>
      )}

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
        <span className="text-xs text-muted-foreground">
          {daInviare.length === 0
            ? "Seleziona almeno una destinazione per procedere con l'aggancio."
            : `${daInviare.length} di ${totale} ${
                daInviare.length === 1 ? "associazione pronta" : "associazioni pronte"
              }. Il ricalcolo avverrà sul file già caricato.`}
        </span>
        <Button
          type="button"
          variant="primary"
          disabled={daInviare.length === 0 || salva.isPending}
          onClick={() => salva.mutate(daInviare)}
        >
          <Link2 className="size-4" />
          {salva.isPending ? "Salvataggio e ricalcolo…" : "Salva associazioni e ricalcola"}
        </Button>
      </div>
    </section>
  );
}

/**
 * Console dei controlli e delle anomalie rilevate.
 */
function ConsoleDeiProblemi({
  problemi,
  collaboratoriCensiti,
  onFiltraCella,
}: {
  problemi: Problema[];
  collaboratoriCensiti?: string[];
  onFiltraCella?: (foglio: string, riga: number | null) => void;
}) {
  const [soloLivello, setSoloLivello] = useState<"TUTTI" | "ERROR" | "WARNING">("TUTTI");
  const [ricerca, setRicerca] = useState("");
  const [copiato, setCopiato] = useState(false);

  const errori = problemi.filter((p) => p.livello === "ERROR").length;
  const avvisi = problemi.length - errori;

  const problemiFiltrati = useMemo(() => {
    return problemi.filter((p) => {
      if (soloLivello !== "TUTTI" && p.livello !== soloLivello) return false;
      if (ricerca.trim()) {
        const query = ricerca.toLowerCase();
        const testo = `${p.foglio} ${p.cella} ${p.messaggio}`.toLowerCase();
        return testo.includes(query);
      }
      return true;
    });
  }, [problemi, soloLivello, ricerca]);

  const copiaProblemi = () => {
    const testo = problemi
      .map(
        (p) =>
          `[${p.livello}] ${p.foglio}${p.cella ? `!${p.cella}` : ""}: ${p.messaggio}`,
      )
      .join("\n");
    void navigator.clipboard.writeText(testo);
    setCopiato(true);
    setTimeout(() => setCopiato(false), 2500);
  };

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-subtle">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold tracking-tight">
              Console Controlli & Integrità
            </h2>
            <span
              className={cn(
                "rounded-full border px-2.5 py-0.5 text-xs font-semibold tabular-nums",
                errori > 0
                  ? "border-danger/30 bg-danger-subtle text-danger"
                  : avvisi > 0
                    ? "border-warn/30 bg-warn-subtle text-warn"
                    : "border-ok/30 bg-ok-subtle text-ok",
              )}
            >
              {errori} {errori === 1 ? "errore" : "errori"} · {avvisi}{" "}
              {avvisi === 1 ? "avviso" : "avvisi"}
            </span>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            Verifica formule, capienze dei progetti, date di competenza e anomalie strutturali.
          </p>
        </div>

        {problemi.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-lg border border-border bg-muted/40 p-0.5">
              {(["TUTTI", "ERROR", "WARNING"] as const).map((liv) => (
                <button
                  key={liv}
                  type="button"
                  onClick={() => setSoloLivello(liv)}
                  className={cn(
                    "rounded-md px-2.5 py-1 text-xs font-medium transition-all",
                    soloLivello === liv
                      ? "bg-card text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {liv === "TUTTI" ? `Tutti (${problemi.length})` : liv === "ERROR" ? `Errori (${errori})` : `Avvisi (${avvisi})`}
                </button>
              ))}
            </div>

            <Button
              type="button"
              variant="secondary"
              className="text-xs h-8 px-2.5"
              onClick={copiaProblemi}
              title="Copia l'elenco dei problemi negli appunti per la correzione dell'Excel"
            >
              {copiato ? (
                <>
                  <Check className="size-3.5 text-ok" /> Copiato
                </>
              ) : (
                <>
                  <Copy className="size-3.5" /> Copia elenco
                </>
              )}
            </Button>
          </div>
        )}
      </div>

      {problemi.length === 0 ? (
        <div className="mt-4 flex items-center gap-3 rounded-lg border border-ok/30 bg-ok-subtle/50 p-4 text-sm text-ok">
          <CheckCircle2 className="size-5 shrink-0" />
          <div>
            <p className="font-semibold">Nessuna anomalia riscontrata</p>
            <p className="text-xs opacity-90">
              Tutte le righe e le formule nei tre fogli sono conformi agli standard contabili.
            </p>
          </div>
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          {problemi.length > 5 && (
            <div className="relative">
              <Search className="absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="search"
                placeholder="Filtra anomalie per foglio, cella o messaggio…"
                value={ricerca}
                onChange={(e) => setRicerca(e.target.value)}
                className="h-8 pl-8 text-xs"
              />
            </div>
          )}

          <div className="max-h-72 overflow-y-auto rounded-lg border border-border/70 bg-muted/20">
            <ul className="divide-y divide-border/50 text-xs">
              {problemiFiltrati.length === 0 ? (
                <li className="p-4 text-center text-muted-foreground">
                  Nessun problema corrisponde ai filtri selezionati.
                </li>
              ) : (
                problemiFiltrati.map((p, i) => {
                  const isError = p.livello === "ERROR";
                  const cellaLabel = p.foglio && p.cella ? `${p.foglio}!${p.cella}` : p.foglio || "Globale";

                  return (
                    <li
                      key={`${p.foglio}-${p.cella}-${i}`}
                      className="flex items-start gap-3 p-2.5 hover:bg-muted/40 transition-colors"
                    >
                      <span
                        className={cn(
                          "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase",
                          isError
                            ? "bg-danger/15 text-danger"
                            : "bg-warn/15 text-warn",
                        )}
                      >
                        {isError ? "Errore" : "Avviso"}
                      </span>

                      <button
                        type="button"
                        onClick={() => onFiltraCella?.(p.foglio, p.riga)}
                        className="shrink-0 rounded border border-border bg-card px-1.5 py-0.5 font-mono text-[11px] font-semibold text-muted-foreground hover:border-accent hover:text-accent transition-colors"
                        title="Clicca per evidenziare nell'anteprima"
                      >
                        {cellaLabel}
                      </button>

                      <span className="flex-1 text-foreground leading-relaxed">
                        {p.messaggio}
                      </span>
                    </li>
                  );
                })
              )}
            </ul>
          </div>
        </div>
      )}

      {collaboratoriCensiti && collaboratoriCensiti.length > 0 && (
        <div className="mt-4 flex items-start gap-2.5 rounded-lg border border-accent/30 bg-accent-subtle/40 p-3 text-xs text-foreground">
          <Info className="mt-0.5 size-4 shrink-0 text-accent" />
          <div>
            <span className="font-semibold text-accent">Nuovi collaboratori censiti:</span>{" "}
            <span>{collaboratoriCensiti.join(", ")}.</span>
            <p className="mt-0.5 text-muted-foreground">
              Questi nominativi sono stati creati automaticamente come figure da completare in
              anagrafica.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Componente principale della Pagina di Importazione.
 */
export function ImportazionePage() {
  const client = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const previewTableRef = useRef<HTMLDivElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [sezione, setSezione] = useState<SezioneId>("PROGETTI");
  const [filtroStatoRiga, setFiltroStatoRiga] = useState<"TUTTE" | "PRONTA" | "DA_ASSOCIARE" | "ERRORE">("TUTTE");
  const [ricercaRiga, setRicercaRiga] = useState("");
  const [storicoAperto, setStoricoAperto] = useState(false);
  const [errore, setErrore] = useState<string | null>(null);
  const [erroreConferma, setErroreConferma] = useState<string | null>(null);

  const storico = useQuery({
    queryKey: ["importazioni"],
    queryFn: () => api.get<{ importazioni: Batch[] }>("/imports/operational"),
  });

  const analizza = useMutation({
    mutationFn: async (scelto: File) => {
      const form = new FormData();
      form.append("file", scelto);
      return api.post<Batch>("/imports/operational/preview", form);
    },
    onSuccess: (dati) => {
      setBatch(dati);
      setErrore(null);
      void client.invalidateQueries({ queryKey: ["importazioni"] });
    },
    onError: (err) =>
      setErrore(err instanceof ApiError ? err.message : "Analisi del file non riuscita."),
  });

  const conferma = useMutation({
    mutationFn: async (corrente: Batch) =>
      api.post<Batch>(`/imports/operational/${corrente.id}/apply`, {
        impronta: corrente.impronta,
      }),
    onSuccess: (dati) => {
      setBatch(dati);
      setErrore(null);
      setErroreConferma(null);
      void client.invalidateQueries();
    },
    onError: (err) =>
      setErroreConferma(err instanceof ApiError ? err.message : "Conferma non riuscita."),
  });

  function scegliFile(nuovo: File | null) {
    setFile(nuovo);
    setBatch(null);
    setErrore(null);
    setErroreConferma(null);
  }

  function handleReset() {
    setFile(null);
    setBatch(null);
    setErrore(null);
    setErroreConferma(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragOver(false);
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile && droppedFile.name.toLowerCase().endsWith(".xlsx")) {
      scegliFile(droppedFile);
    } else {
      setErrore("Formato file non supportato. Selezionare un file Excel con estensione .xlsx");
    }
  }

  const report = batch?.report ?? null;
  const problemi = report?.problemi ?? [];
  const errori = problemi.filter((p) => p.livello === "ERROR").length;
  const applicato = batch?.stato === "APPLIED";
  const daAssociare = useMemo(() => report?.da_associare ?? [], [report]);
  const bloccanti = batch?.errori_bloccanti ?? [];

  // Righe della sezione attiva con filtri di ricerca e stato
  const righeSezione = useMemo(() => {
    return (batch?.righe ?? []).filter((r) => {
      if (r.sezione !== sezione) return false;
      if (filtroStatoRiga !== "TUTTE" && r.stato !== filtroStatoRiga) return false;
      if (ricercaRiga.trim()) {
        const query = ricercaRiga.toLowerCase();
        const testo = `${r.destinazione_excel} ${r.destinazione_risolta ?? ""} ${r.collaboratore_excel} ${r.utente ?? ""} ${r.descrizione}`.toLowerCase();
        return testo.includes(query);
      }
      return true;
    });
  }, [batch?.righe, sezione, filtroStatoRiga, ricercaRiga]);

  // Conteggi righe per sezione attiva
  const conteggiStatoSezione = useMemo(() => {
    const righeDellaSezione = (batch?.righe ?? []).filter((r) => r.sezione === sezione);
    return {
      totali: righeDellaSezione.length,
      pronte: righeDellaSezione.filter((r) => r.stato === "PRONTA").length,
      daAssociare: righeDellaSezione.filter((r) => r.stato === "DA_ASSOCIARE").length,
      errore: righeDellaSezione.filter((r) => r.stato === "ERRORE").length,
    };
  }, [batch?.righe, sezione]);

  const totaliEsclusi = useMemo(() => {
    return (report?.sezioni ?? []).reduce((acc, s) => acc + s.righe_di_totale_escluse, 0);
  }, [report?.sezioni]);

  const switchSezioneAndScroll = (id: SezioneId) => {
    setSezione(id);
    previewTableRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <section className="space-y-6 pb-12">
      {/* Intestazione pagina */}
      <PageHeader
        eyebrow="Consuntivi Settimanali"
        title="Importazione Estratto Operativo"
        description="Carica il foglio Excel settimanale per inserire i nuovi consuntivi su Progetti, Wallet e Organico Allargato in modalità incrementale."
        actions={
          (file || batch) && (
            <Button
              type="button"
              variant="secondary"
              onClick={handleReset}
              className="text-xs"
              title="Resetta l'anteprima e carica un nuovo file"
            >
              <RotateCcw className="size-3.5" />
              Nuova importazione
            </Button>
          )
        }
      />

      {/* Stepper di Avanzamento */}
      <WorkflowStepper
        batch={batch}
        daAssociareCount={daAssociare.length}
        erroriCount={errori}
      />

      {/* Passaggio 1 — Selezione e caricamento del file */}
      <div className="rounded-xl border border-border bg-card p-5 shadow-subtle">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold tracking-tight">1. Selezione File Excel</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              File <code>.xlsx</code> strutturato con i fogli <strong>Progetti</strong>,{" "}
              <strong>Wallet</strong> e <strong>Organico_Allargato</strong>.
            </p>
          </div>
          {file && (
            <span className="rounded-full border border-ok/30 bg-ok-subtle px-2.5 py-0.5 text-xs font-semibold text-ok">
              File selezionato
            </span>
          )}
        </div>

        <input
          ref={inputRef}
          type="file"
          accept=".xlsx"
          className="hidden"
          onChange={(e) => scegliFile(e.target.files?.[0] ?? null)}
        />

        {!file ? (
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragOver(true);
            }}
            onDragLeave={() => setIsDragOver(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            className={cn(
              "mt-4 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center transition-all",
              isDragOver
                ? "border-accent bg-accent-subtle/50 scale-[0.99]"
                : "border-border/80 bg-muted/20 hover:border-accent/60 hover:bg-muted/40",
            )}
          >
            <div className="flex size-14 items-center justify-center rounded-2xl bg-accent-subtle text-accent shadow-sm">
              <UploadCloud className="size-7" />
            </div>
            <p className="mt-3 text-sm font-semibold text-foreground">
              Trascina qui l'estratto Excel oppure clicca per selezionarlo
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Formato supportato: cartelle di lavoro <code>.xlsx</code> (fino a 10 MB)
            </p>
            <Button
              type="button"
              variant="secondary"
              className="mt-4 pointer-events-none"
              tabIndex={-1}
            >
              <FileSpreadsheet className="size-4" /> Sfoglia file
            </Button>
          </div>
        ) : (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border bg-muted/20 p-4">
            <div className="flex items-center gap-3.5">
              <div className="flex size-12 items-center justify-center rounded-xl bg-ok-subtle text-ok shadow-sm">
                <FileSpreadsheet className="size-6" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">{file.name}</p>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>{formatDimensione(file.size)}</span>
                  <span>·</span>
                  <span>Pronto per l'analisi</span>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="secondary"
                disabled={analizza.isPending}
                onClick={() => inputRef.current?.click()}
              >
                Cambia file
              </Button>
              <Button
                type="button"
                variant="primary"
                disabled={analizza.isPending || Boolean(batch)}
                onClick={() => analizza.mutate(file)}
              >
                <Upload className="size-4" />
                {analizza.isPending
                  ? "Analisi in corso…"
                  : batch
                    ? "File già analizzato"
                    : "Analizza estratto"}
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Messaggio di errore analisi */}
      {errore && (
        <div className="rounded-xl border border-danger/30 bg-danger-subtle p-4 text-sm text-danger flex items-start gap-3">
          <AlertCircle className="size-5 shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold">Errore durante l'elaborazione del file</p>
            <p className="text-xs mt-0.5">{errore}</p>
          </div>
        </div>
      )}

      {/* Indicatore di caricamento analisi */}
      {analizza.isPending && (
        <div className="rounded-xl border border-border bg-card p-8 shadow-subtle text-center">
          <LoadingState rows={3} />
          <p className="mt-4 text-sm font-medium text-muted-foreground">
            Lettura dei fogli Excel, analisi formule e confronto con l'anagrafica in corso…
          </p>
        </div>
      )}

      {/* Risultati dell'Analisi (quando il batch è disponibile) */}
      {batch && (
        <>
          {/* Cruscotto KPI Esecutivo */}
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <KpiCard
                label="Righe Dati Rilevate"
                value={report?.totale_righe ?? 0}
                hint="Escluse formule e intestazioni"
                tooltip="Numero totale di righe consuntivo estratte dai tre fogli operativi."
              />
              <KpiCard
                label="Volume Giornate"
                value={report?.totale_giornate ? formatDays(report.totale_giornate) : "—"}
                hint="Consuntivi settimanali"
                tooltip="Somma delle giornate totali conteggiate nel file."
              />
              <KpiCard
                label="Stato Validazione"
                value={
                  applicato
                    ? "Applicato"
                    : batch.confermabile
                      ? "Conforme"
                      : daAssociare.length > 0
                        ? `${daAssociare.length} Da Riconciliare`
                        : `${errori} Errori`
                }
                tone={applicato || batch.confermabile ? "ok" : daAssociare.length > 0 ? "warn" : "danger"}
                hint={
                  applicato
                    ? "Movimenti salvati nel ledger"
                    : batch.confermabile
                      ? "Tutti i vincoli superati"
                      : daAssociare.length > 0
                        ? "Richiede associazione manuale"
                        : "Correzione file necessaria"
                }
              />
              <KpiCard
                label="Totali Esclusi in Sicurezza"
                value={totaliEsclusi}
                hint="Formule subtotali ignorate"
                tooltip="Righe finali di totale o subtotale individuate ed escluse per evitare doppi conteggi."
              />
            </div>

            {/* Schede sintetiche per Sezione (Progetti, Wallet, Organico) */}
            <div className="grid gap-3 md:grid-cols-3">
              {(report?.sezioni ?? []).map((s) => {
                const isSelected = sezione === s.sezione;
                const SezioneIcon =
                  SEZIONI.find((x) => x.id === s.sezione)?.icon ?? FolderGit2;

                // Controlla se la sezione ha errori bloccanti associati al suo foglio
                const erroriSezione = problemi.filter(
                  (p) =>
                    p.livello === "ERROR" &&
                    (p.foglio.toLowerCase().includes(s.etichetta.toLowerCase()) ||
                      p.foglio.toLowerCase().includes(s.sezione.toLowerCase()) ||
                      (s.sezione === "ORGANICO" &&
                        p.foglio.toLowerCase().includes("organico"))),
                );
                const hasErroriBloccanti = erroriSezione.length > 0;

                return (
                  <div
                    key={s.sezione}
                    onClick={() => switchSezioneAndScroll(s.sezione)}
                    className={cn(
                      "cursor-pointer rounded-xl border p-4 transition-all hover:border-accent/60",
                      isSelected
                        ? "border-accent bg-accent-subtle/30 ring-1 ring-accent"
                        : hasErroriBloccanti
                          ? "border-danger/40 bg-card shadow-subtle ring-1 ring-danger/20"
                          : "border-border bg-card shadow-subtle",
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span
                          className={cn(
                            "flex size-8 items-center justify-center rounded-lg",
                            isSelected
                              ? "bg-accent text-accent-foreground"
                              : hasErroriBloccanti
                                ? "bg-danger/15 text-danger"
                                : "bg-muted text-muted-foreground",
                          )}
                        >
                          <SezioneIcon className="size-4" />
                        </span>
                        <h3 className="font-semibold text-foreground text-sm">{s.etichetta}</h3>
                      </div>
                      <span className="font-mono text-xs font-semibold tabular-nums text-foreground">
                        {formatDays(s.giornate)}
                      </span>
                    </div>

                    <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
                      <span>{s.righe_lette} righe totali</span>
                      <span className={cn(hasErroriBloccanti ? "text-danger font-medium" : "text-ok font-medium")}>
                        {s.righe_importabili} pronte
                      </span>
                    </div>

                    {/* Barra di avanzamento ripartizione */}
                    <div className="mt-2 flex h-1.5 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className={cn(hasErroriBloccanti ? "bg-danger" : "bg-ok")}
                        style={{
                          width: `${s.righe_lette ? (s.righe_importabili / s.righe_lette) * 100 : 0}%`,
                        }}
                      />
                      <div
                        className="bg-warn"
                        style={{
                          width: `${s.righe_lette ? (s.righe_da_associare / s.righe_lette) * 100 : 0}%`,
                        }}
                      />
                      <div
                        className="bg-danger"
                        style={{
                          width: `${s.righe_lette ? (s.righe_in_errore / s.righe_lette) * 100 : 0}%`,
                        }}
                      />
                    </div>

                    <div className="mt-2.5 flex items-center gap-2 text-[11px]">
                      {hasErroriBloccanti ? (
                        <span className="text-danger flex items-center gap-1 font-semibold">
                          <AlertCircle className="size-3" />
                          {erroriSezione.length}{" "}
                          {erroriSezione.length === 1 ? "blocco capienza" : "blocchi capienza"}
                        </span>
                      ) : (
                        <>
                          {s.righe_da_associare > 0 && (
                            <span className="rounded bg-warn-subtle px-1.5 py-0.5 font-medium text-warn">
                              {s.righe_da_associare} da associare
                            </span>
                          )}
                          {s.righe_in_errore > 0 && (
                            <span className="rounded bg-danger-subtle px-1.5 py-0.5 font-medium text-danger">
                              {s.righe_in_errore} errori
                            </span>
                          )}
                          {s.righe_da_associare === 0 && s.righe_in_errore === 0 && (
                            <span className="text-ok flex items-center gap-1 font-medium">
                              <Check className="size-3" /> Tutte conformi
                            </span>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Console dei Problemi */}
          <ConsoleDeiProblemi
            problemi={problemi}
            collaboratoriCensiti={report?.collaboratori_censiti}
            onFiltraCella={(foglio) => {
              const matchedSezione = SEZIONI.find(
                (s) => s.label.toLowerCase() === foglio.toLowerCase() || s.id.toLowerCase() === foglio.toLowerCase(),
              );
              if (matchedSezione) {
                switchSezioneAndScroll(matchedSezione.id);
              }
            }}
          />

          {/* Riconciliazione Voci Mancanti (Inline) */}
          {!applicato && daAssociare.length > 0 && (
            <SezioneRiconciliazioneInline
              batch={batch}
              gruppi={daAssociare}
              onAggiornato={setBatch}
            />
          )}

          {/* Anteprima Dettaglio Righe */}
          <div
            ref={previewTableRef}
            className="rounded-xl border border-border bg-card p-5 shadow-subtle"
          >
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
              <div>
                <h2 className="text-base font-semibold tracking-tight">
                  {daAssociare.length > 0 ? "4" : "3"}. Anteprima Dettaglio Movimenti
                </h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  Ispezione riga per riga dei dati estratti da applicare nel ledger.
                </p>
              </div>

              {/* Selettore schede per Sezione */}
              <div className="flex flex-wrap gap-1.5 rounded-lg border border-border bg-muted/30 p-1">
                {SEZIONI.map((s) => {
                  const conta = (batch.righe ?? []).filter((r) => r.sezione === s.id).length;
                  const isActive = sezione === s.id;
                  const SIcon = s.icon;

                  return (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => setSezione(s.id)}
                      className={cn(
                        "flex items-center gap-2 rounded-md px-3 py-1.5 text-xs font-semibold transition-all",
                        isActive
                          ? "bg-card text-foreground shadow-sm"
                          : "text-muted-foreground hover:text-foreground",
                      )}
                    >
                      <SIcon className="size-3.5" />
                      {s.label}
                      <span
                        className={cn(
                          "rounded-full px-1.5 py-0.2 text-[10px]",
                          isActive ? "bg-accent/15 text-accent" : "bg-muted text-muted-foreground",
                        )}
                      >
                        {conta}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Toolbar di ricerca e filtro per stato riga */}
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <div className="relative min-w-[16rem] flex-1 max-w-sm">
                <Search className="absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  type="search"
                  placeholder="Cerca collaboratore, descrizione, codice…"
                  value={ricercaRiga}
                  onChange={(e) => setRicercaRiga(e.target.value)}
                  className="h-8 pl-8 text-xs"
                />
              </div>

              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                <button
                  type="button"
                  onClick={() => setFiltroStatoRiga("TUTTE")}
                  className={cn(
                    "rounded-md border px-2.5 py-1 font-medium transition-all",
                    filtroStatoRiga === "TUTTE"
                      ? "border-accent bg-accent text-accent-foreground"
                      : "border-input bg-card text-muted-foreground hover:text-foreground",
                  )}
                >
                  Tutte ({conteggiStatoSezione.totali})
                </button>
                <button
                  type="button"
                  onClick={() => setFiltroStatoRiga("PRONTA")}
                  className={cn(
                    "rounded-md border px-2.5 py-1 font-medium transition-all",
                    filtroStatoRiga === "PRONTA"
                      ? "border-ok bg-ok text-white"
                      : "border-input bg-card text-muted-foreground hover:text-foreground",
                  )}
                >
                  Pronte ({conteggiStatoSezione.pronte})
                </button>
                {conteggiStatoSezione.daAssociare > 0 && (
                  <button
                    type="button"
                    onClick={() => setFiltroStatoRiga("DA_ASSOCIARE")}
                    className={cn(
                      "rounded-md border px-2.5 py-1 font-medium transition-all",
                      filtroStatoRiga === "DA_ASSOCIARE"
                        ? "border-warn bg-warn text-white"
                        : "border-input bg-card text-muted-foreground hover:text-foreground",
                    )}
                  >
                    Da associare ({conteggiStatoSezione.daAssociare})
                  </button>
                )}
                {conteggiStatoSezione.errore > 0 && (
                  <button
                    type="button"
                    onClick={() => setFiltroStatoRiga("ERRORE")}
                    className={cn(
                      "rounded-md border px-2.5 py-1 font-medium transition-all",
                      filtroStatoRiga === "ERRORE"
                        ? "border-danger bg-danger text-white"
                        : "border-input bg-card text-muted-foreground hover:text-foreground",
                    )}
                  >
                    In errore ({conteggiStatoSezione.errore})
                  </button>
                )}
              </div>
            </div>

            {/* Tabella righe */}
            {righeSezione.length === 0 ? (
              <div className="mt-4 py-8">
                <EmptyState
                  title="Nessun movimento trovato"
                  detail="Nessuna riga corrisponde ai filtri di ricerca impostati per questa sezione."
                />
              </div>
            ) : (
              <div className="mt-4 overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-left text-xs">
                  <thead className="bg-muted/40 uppercase tracking-wider text-muted-foreground font-semibold">
                    <tr>
                      <th className="py-2.5 px-3">Cella</th>
                      <th className="py-2.5 px-3">Destinazione Excel</th>
                      <th className="py-2.5 px-3">Destinazione Risolta</th>
                      <th className="py-2.5 px-3">Collaboratore</th>
                      <th className="py-2.5 px-3">Data</th>
                      <th className="py-2.5 px-3 text-right">Giornate</th>
                      <th className="py-2.5 px-3">Descrizione</th>
                      <th className="py-2.5 px-3 text-center">Stato</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {righeSezione.map((r) => {
                      const cfg = STATO_RIGA_CONFIG[r.stato];
                      return (
                        <tr key={r.id} className="hover:bg-muted/20 transition-colors">
                          <td className="py-2.5 px-3 font-mono text-[11px] text-muted-foreground">
                            {r.foglio}!{r.riga_excel}
                          </td>
                          <td className="py-2.5 px-3 font-medium text-foreground">
                            {r.destinazione_excel || "—"}
                          </td>
                          <td className="py-2.5 px-3">
                            {r.destinazione_risolta ? (
                              <span className="font-medium text-foreground">
                                {r.destinazione_risolta}
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 rounded bg-warn-subtle px-1.5 py-0.5 text-[11px] font-semibold text-warn">
                                <AlertTriangle className="size-3" /> Da associare
                              </span>
                            )}
                          </td>
                          <td className="py-2.5 px-3">
                            <span className="font-medium text-foreground">
                              {r.collaboratore_excel}
                            </span>
                            {r.utente && (
                              <span className="block text-[11px] text-muted-foreground">
                                {r.utente}
                              </span>
                            )}
                          </td>
                          <td className="py-2.5 px-3 whitespace-nowrap text-muted-foreground">
                            {formatData(r.data)}
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono font-semibold tabular-nums text-foreground">
                            {formatDays(r.giornate)}
                          </td>
                          <td className="py-2.5 px-3 max-w-xs truncate text-muted-foreground" title={r.descrizione}>
                            {r.descrizione || "—"}
                          </td>
                          <td className="py-2.5 px-3 text-center">
                            <span
                              className={cn(
                                "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold",
                                cfg.badgeClass,
                              )}
                            >
                              <span className={cn("size-1.5 rounded-full", cfg.dotClass)} />
                              {cfg.label}
                            </span>
                            {r.motivazione && (
                              <p className="mt-0.5 text-[10px] text-muted-foreground">
                                {r.motivazione}
                              </p>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            <div className="mt-2 text-right text-[11px] text-muted-foreground">
              Mostrate {righeSezione.length} di {conteggiStatoSezione.totali} righe in {sezione}
            </div>
          </div>

          {/* Stazione di Conferma Finale */}
          <div className="rounded-xl border border-border bg-card p-5 shadow-subtle">
            <h2 className="text-base font-semibold tracking-tight">
              {daAssociare.length > 0 ? "5" : "4"}. Conferma & Scrittura nel Ledger
            </h2>

            {applicato ? (
              <div className="mt-4 rounded-xl border border-ok/30 bg-ok-subtle/50 p-5 text-ok">
                <div className="flex items-center gap-3">
                  <span className="flex size-10 items-center justify-center rounded-xl bg-ok/20">
                    <CheckCircle2 className="size-6 text-ok" />
                  </span>
                  <div>
                    <h3 className="text-base font-bold text-ok">
                      Importazione applicata con successo!
                    </h3>
                    {batch.report?.applicato && (
                      <p className="text-xs text-foreground mt-0.5">
                        Registrati <strong>{batch.report.applicato.movimenti}</strong> consuntivi per un
                        totale di <strong>{formatDays(batch.report.applicato.giornate)}</strong> da{" "}
                        <strong>{batch.report.applicato.operatore}</strong> in data{" "}
                        {formatIstante(batch.report.applicato.istante)}.
                      </p>
                    )}
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-ok/20 pt-3 text-xs text-muted-foreground">
                  <span className="font-mono">ID Batch: {batch.id}</span>
                  <Button type="button" variant="secondary" onClick={handleReset}>
                    Avvia una nuova importazione
                  </Button>
                </div>
              </div>
            ) : (
              <div className="mt-3 space-y-4">
                <p className="text-xs text-muted-foreground">
                  {batch.confermabile
                    ? "Tutte le righe sono state validate e riconciliate. La conferma applica i movimenti in modalità append su Progetti, Wallet e Canone."
                    : "La conferma finale sarà abilitata solo quando tutte le voci saranno state riconciliate e gli errori risolti."}
                </p>

                {/* Banner di blocco esplicito con motivazioni e guida alla risoluzione */}
                {!batch.confermabile && (
                  <div className="space-y-3">
                    <div className="rounded-xl border border-danger/40 bg-danger-subtle/30 p-4">
                      <div className="flex items-center gap-2 text-sm font-semibold text-danger">
                        <AlertCircle className="size-4 shrink-0" />
                        <span>Blocchi contabili che impediscono la conferma:</span>
                      </div>
                      <ul className="mt-2.5 space-y-1.5 text-xs text-foreground list-disc pl-5">
                        {daAssociare.length > 0 && (
                          <li>
                            <strong>{daAssociare.length}</strong>{" "}
                            {daAssociare.length === 1
                              ? "associazione mancante"
                              : "associazioni mancanti"}{" "}
                            da completare nel passaggio 3 sopra.
                          </li>
                        )}
                        {bloccanti.map((m, i) => (
                          <li key={i} className="font-medium text-danger">
                            {m}
                          </li>
                        ))}
                        {errori > 0 && bloccanti.length === 0 && (
                          <li>
                            <strong>{errori}</strong>{" "}
                            {errori === 1 ? "errore bloccante" : "errori bloccanti"} rilevati nel
                            file Excel (vedi Console Controlli).
                          </li>
                        )}
                      </ul>
                    </div>

                    {/* Guida all'azione per l'utente */}
                    <div className="rounded-xl border border-border bg-muted/30 p-4 text-xs">
                      <p className="font-semibold text-foreground flex items-center gap-1.5">
                        <Info className="size-3.5 text-accent" />
                        Cosa fare per sbloccare la conferma:
                      </p>
                      <ul className="mt-2 space-y-1 text-muted-foreground list-disc pl-5">
                        {bloccanti.some((b) => b.includes("Capienza superata")) && (
                          <>
                            <li>
                              <strong className="text-foreground">Verifica duplicati nell'Excel:</strong> molti consuntivi potrebbero essere già stati caricati a sistema (vedi avvisi <em>"Riga già presente"</em> nella Console). Rimuovere le righe duplicate dall'Excel e ricaricare il file.
                            </li>
                            <li>
                              <strong className="text-foreground">Aumento budget / capienza:</strong> se il consumo extra è autorizzato, incrementare il budget del progetto nella sezione <em>Progetti</em> o la capienza dell'allocazione nella sezione <em>Wallet</em>, poi ripetere l'analisi.
                            </li>
                          </>
                        )}
                        {daAssociare.length > 0 && (
                          <li>
                            <strong className="text-foreground">Riconciliazione:</strong> completare le associazioni delle voci mancanti al passaggio 3.
                          </li>
                        )}
                      </ul>
                    </div>
                  </div>
                )}

                {erroreConferma && (
                  <div className="rounded-lg border border-danger/30 bg-danger-subtle p-3 text-xs text-danger">
                    {erroreConferma}
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-3 pt-2">
                  <Button
                    type="button"
                    variant="primary"
                    disabled={!batch.confermabile || conferma.isPending}
                    onClick={() => conferma.mutate(batch)}
                    className="min-h-10 px-5"
                  >
                    <CheckCircle2 className="size-4" />
                    {conferma.isPending
                      ? "Scrittura movimenti in corso…"
                      : "Conferma e applica importazione"}
                  </Button>

                  {!batch.confermabile && (
                    <span className="text-xs text-danger font-medium flex items-center gap-1">
                      <AlertCircle className="size-3.5 shrink-0" />
                      Importazione bloccata da errori contabili di capienza.
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        </>
      )}

      {/* Storico delle Importazioni Pregresse */}
      <div className="rounded-xl border border-border bg-card shadow-subtle overflow-hidden">
        <button
          type="button"
          onClick={() => setStoricoAperto((p) => !p)}
          className="w-full flex items-center justify-between p-5 text-left hover:bg-muted/20 transition-colors"
        >
          <div className="flex items-center gap-2.5">
            <span className="flex size-8 items-center justify-center rounded-lg bg-muted text-muted-foreground">
              <History className="size-4" />
            </span>
            <div>
              <h2 className="text-sm font-semibold tracking-tight text-foreground">
                Storico delle Importazioni
              </h2>
              <p className="text-xs text-muted-foreground">
                Registro dei file precedentemente caricati e applicati.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>
              {(storico.data?.importazioni ?? []).length}{" "}
              {(storico.data?.importazioni ?? []).length === 1 ? "operazione" : "operazioni"}
            </span>
            {storicoAperto ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
          </div>
        </button>

        {storicoAperto && (
          <div className="border-t border-border p-5 pt-2">
            {storico.isLoading ? (
              <LoadingState rows={3} />
            ) : storico.isError ? (
              <ErrorState title="Storico non disponibile" />
            ) : (storico.data?.importazioni ?? []).length === 0 ? (
              <EmptyState title="Nessuna importazione registrata a sistema" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-muted-foreground uppercase tracking-wider font-semibold border-b border-border">
                    <tr>
                      <th className="py-2 px-3">File Excel</th>
                      <th className="py-2 px-3">Stato</th>
                      <th className="py-2 px-3">Caricato il</th>
                      <th className="py-2 px-3">Operatore</th>
                      <th className="py-2 px-3">Applicato il</th>
                      <th className="py-2 px-3 text-right">Movimenti</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {(storico.data?.importazioni ?? []).map((b) => (
                      <tr key={b.id} className="hover:bg-muted/20 transition-colors">
                        <td className="py-2.5 px-3 font-medium text-foreground">
                          {b.file || "—"}
                        </td>
                        <td className="py-2.5 px-3">
                          <span
                            className={cn(
                              "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold",
                              b.stato === "APPLIED"
                                ? "border-ok/30 bg-ok-subtle text-ok"
                                : b.stato === "PREVIEW"
                                  ? "border-accent/30 bg-accent-subtle text-accent"
                                  : "border-border bg-muted text-muted-foreground",
                            )}
                          >
                            {b.stato_etichetta}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 whitespace-nowrap text-muted-foreground">
                          {formatIstante(b.creato_il)}
                        </td>
                        <td className="py-2.5 px-3 text-muted-foreground">{b.operatore ?? "—"}</td>
                        <td className="py-2.5 px-3 whitespace-nowrap text-muted-foreground">
                          {formatIstante(b.applicato_il)}
                        </td>
                        <td className="py-2.5 px-3 text-right font-mono font-semibold tabular-nums text-foreground">
                          {b.report?.applicato?.movimenti ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
