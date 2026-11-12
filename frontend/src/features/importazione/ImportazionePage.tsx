/**
 * Importazione settimanale dei consuntivi dall'estratto operativo.
 *
 * Sostituisce la pagina "Riconciliazione PPM". Il flusso è quello del §7 del piano:
 * caricamento, analisi, anteprima a tre schede con la console dei problemi, conferma,
 * esito e storico. L'analisi non crea consuntivi: li crea solo la conferma.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, FileSpreadsheet, Info, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/Controls";
import { PageHeader } from "@/components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/UiState";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

const SEZIONI = [
  { id: "PROGETTI", label: "Progetti" },
  { id: "WALLET", label: "Wallet" },
  { id: "ORGANICO", label: "Organico allargato" },
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
  report: {
    sezioni?: Riepilogo[];
    problemi?: Problema[];
    collaboratori_censiti?: string[];
    totale_righe?: number;
    totale_giornate?: string;
    applicato?: { movimenti: number; giornate: string; operatore: string; istante: string };
  } | null;
  righe?: Riga[];
}

const STATO_RIGA: Record<Riga["stato"], { label: string; tone: string }> = {
  PRONTA: { label: "Pronta", tone: "text-ok" },
  DA_ASSOCIARE: { label: "Da associare", tone: "text-warning" },
  ERRORE: { label: "Errore", tone: "text-danger" },
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

export function ImportazionePage() {
  const client = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [sezione, setSezione] = useState<SezioneId>("PROGETTI");
  const [soloProblemi, setSoloProblemi] = useState<"TUTTI" | "ERROR" | "WARNING">("TUTTI");
  const [errore, setErrore] = useState<string | null>(null);

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
      // I consuntivi nuovi cambiano progetti, wallet, canone, dashboard e analisi costi.
      void client.invalidateQueries();
    },
    onError: (err) => setErrore(err instanceof ApiError ? err.message : "Conferma non riuscita."),
  });

  function scegli(nuovo: File | null) {
    setFile(nuovo);
    // Cambiare file annulla l'anteprima precedente: non deve restare a schermo
    // un'anteprima che non corrisponde al file selezionato.
    setBatch(null);
    setErrore(null);
  }

  const report = batch?.report ?? null;
  const problemi = report?.problemi ?? [];
  const problemiVisibili =
    soloProblemi === "TUTTI" ? problemi : problemi.filter((p) => p.livello === soloProblemi);
  const errori = problemi.filter((p) => p.livello === "ERROR").length;
  const avvisi = problemi.length - errori;
  const applicato = batch?.stato === "APPLIED";
  const righeSezione = (batch?.righe ?? []).filter((r) => r.sezione === sezione);

  return (
    <section className="space-y-6">
      <PageHeader
        eyebrow="Consuntivi"
        title="Importazione"
        description="Carica l'estratto operativo settimanale: i consuntivi si aggiungono a quelli già presenti, senza sostituirli."
      />

      {/* Passaggio 1 — caricamento */}
      <div className="rounded-xl border border-border bg-card p-5 shadow-subtle">
        <h2 className="text-sm font-semibold">1. Caricamento</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          File <code>.xlsx</code> con i tre fogli <strong>Progetti</strong>, <strong>Wallet</strong>{" "}
          e <strong>Organico_Allargato</strong>. Le colonne sono abbinate per nome: intestazioni
          nella prima riga, dati dalla seconda.
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <input
            ref={inputRef}
            type="file"
            accept=".xlsx"
            className="hidden"
            onChange={(e) => scegli(e.target.files?.[0] ?? null)}
          />
          <Button type="button" variant="secondary" onClick={() => inputRef.current?.click()}>
            <FileSpreadsheet className="size-4" /> Scegli file
          </Button>
          {file ? (
            <span className="text-sm">
              <strong>{file.name}</strong>{" "}
              <span className="text-muted-foreground">({formatDimensione(file.size)})</span>
            </span>
          ) : (
            <span className="text-sm text-muted-foreground">Nessun file selezionato</span>
          )}
          <Button
            type="button"
            variant="primary"
            disabled={!file || analizza.isPending}
            onClick={() => file && analizza.mutate(file)}
          >
            <Upload className="size-4" />
            {analizza.isPending ? "Analisi in corso…" : "Analizza file"}
          </Button>
        </div>
      </div>

      {errore ? (
        <div className="rounded-lg border border-danger/30 bg-danger-subtle p-3 text-sm text-danger">
          {errore}
        </div>
      ) : null}

      {analizza.isPending ? <LoadingState rows={3} /> : null}

      {batch ? (
        <>
          {/* Passaggio 2 — riepiloghi */}
          <div className="rounded-xl border border-border bg-card p-5 shadow-subtle">
            <h2 className="text-sm font-semibold">2. Riepilogo per sezione</h2>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="py-2">Sezione</th>
                    <th className="py-2 text-right">Lette</th>
                    <th className="py-2 text-right">Importabili</th>
                    <th className="py-2 text-right">Da associare</th>
                    <th className="py-2 text-right">In errore</th>
                    <th className="py-2 text-right">Totali esclusi</th>
                    <th className="py-2 text-right">Giornate</th>
                  </tr>
                </thead>
                <tbody>
                  {(report?.sezioni ?? []).map((s) => (
                    <tr key={s.sezione} className="border-t border-border">
                      <td className="py-2 font-medium">{s.etichetta}</td>
                      <td className="py-2 text-right">{s.righe_lette}</td>
                      <td className="py-2 text-right text-ok">{s.righe_importabili}</td>
                      <td className="text-warning py-2 text-right">{s.righe_da_associare}</td>
                      <td className="py-2 text-right text-danger">{s.righe_in_errore}</td>
                      <td className="py-2 text-right">{s.righe_di_totale_escluse}</td>
                      <td className="py-2 text-right font-mono">{s.giornate}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Console dei problemi */}
          <div className="rounded-xl border border-border bg-card p-5 shadow-subtle">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-sm font-semibold">
                Console dei problemi{" "}
                <span className="text-muted-foreground">
                  ({errori} {errori === 1 ? "errore" : "errori"}, {avvisi}{" "}
                  {avvisi === 1 ? "avviso" : "avvisi"})
                </span>
              </h2>
              <div className="flex gap-2">
                {(["TUTTI", "ERROR", "WARNING"] as const).map((livello) => (
                  <button
                    key={livello}
                    type="button"
                    onClick={() => setSoloProblemi(livello)}
                    className={cn(
                      "rounded-md border px-2 py-1 text-xs",
                      soloProblemi === livello
                        ? "border-accent bg-accent text-accent-foreground"
                        : "border-input",
                    )}
                  >
                    {livello === "TUTTI" ? "Tutti" : livello === "ERROR" ? "Errori" : "Avvisi"}
                  </button>
                ))}
              </div>
            </div>
            {problemiVisibili.length === 0 ? (
              <p className="mt-3 flex items-center gap-2 text-sm text-ok">
                <CheckCircle2 className="size-4" /> Nessun problema da segnalare.
              </p>
            ) : (
              <ul className="mt-3 space-y-1 font-mono text-xs">
                {problemiVisibili.map((p, i) => (
                  <li
                    key={`${p.foglio}-${p.cella}-${i}`}
                    className="flex gap-2 border-b border-border/50 py-1"
                  >
                    <span
                      className={cn(
                        "shrink-0 font-semibold",
                        p.livello === "ERROR" ? "text-danger" : "text-warning",
                      )}
                    >
                      {p.livello === "ERROR" ? "ERRORE " : "AVVISO "}
                    </span>
                    <span className="shrink-0 text-muted-foreground">
                      {p.foglio && p.cella ? `${p.foglio}!${p.cella}` : p.foglio || "—"}
                    </span>
                    <span className="font-sans">{p.messaggio}</span>
                  </li>
                ))}
              </ul>
            )}
            {report?.collaboratori_censiti?.length ? (
              <p className="border-warning/30 bg-warning-subtle text-warning mt-3 flex items-start gap-2 rounded-md border p-2 text-xs">
                <Info className="mt-0.5 size-4 shrink-0" />
                <span>
                  Collaboratori censiti dall'importazione:{" "}
                  <strong>{report.collaboratori_censiti.join(", ")}</strong>. Vanno completati in
                  anagrafica.
                </span>
              </p>
            ) : null}
          </div>

          {/* Passaggio 3 — anteprima */}
          <div className="rounded-xl border border-border bg-card p-5 shadow-subtle">
            <h2 className="text-sm font-semibold">3. Anteprima</h2>
            <div className="mt-3 flex gap-2">
              {SEZIONI.map((s) => {
                const conta = (batch.righe ?? []).filter((r) => r.sezione === s.id).length;
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => setSezione(s.id)}
                    className={cn(
                      "rounded-md border px-3 py-1.5 text-sm",
                      sezione === s.id
                        ? "border-accent bg-accent text-accent-foreground"
                        : "border-input",
                    )}
                  >
                    {s.label} <span className="text-xs opacity-70">({conta})</span>
                  </button>
                );
              })}
            </div>
            {righeSezione.length === 0 ? (
              <EmptyState title="Nessuna riga in questa sezione" />
            ) : (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs uppercase text-muted-foreground">
                    <tr>
                      <th className="py-2">Riga</th>
                      <th className="py-2">Destinazione nell'Excel</th>
                      <th className="py-2">Destinazione risolta</th>
                      <th className="py-2">Collaboratore</th>
                      <th className="py-2">Utente</th>
                      <th className="py-2">Data</th>
                      <th className="py-2 text-right">Giornate</th>
                      <th className="py-2">Descrizione</th>
                      <th className="py-2">Esito</th>
                    </tr>
                  </thead>
                  <tbody>
                    {righeSezione.map((r) => (
                      <tr key={r.id} className="border-t border-border align-top">
                        <td className="py-2 font-mono text-xs text-muted-foreground">
                          {r.foglio}!{r.riga_excel}
                        </td>
                        <td className="py-2">{r.destinazione_excel || "—"}</td>
                        <td className="py-2">
                          {r.destinazione_risolta ?? (
                            <span className="text-warning">da associare</span>
                          )}
                        </td>
                        <td className="py-2">{r.collaboratore_excel}</td>
                        <td className="py-2">{r.utente ?? "—"}</td>
                        <td className="whitespace-nowrap py-2">{formatData(r.data)}</td>
                        <td className="py-2 text-right font-mono">{r.giornate}</td>
                        <td className="max-w-[22rem] py-2">{r.descrizione}</td>
                        <td className="py-2">
                          <span className={cn("text-xs font-semibold", STATO_RIGA[r.stato].tone)}>
                            {STATO_RIGA[r.stato].label}
                          </span>
                          {r.motivazione ? (
                            <p className="mt-1 text-xs text-muted-foreground">{r.motivazione}</p>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Passaggio 4 e 5 — conferma ed esito */}
          <div className="rounded-xl border border-border bg-card p-5 shadow-subtle">
            <h2 className="text-sm font-semibold">4. Conferma</h2>
            {applicato ? (
              <div className="mt-3 rounded-lg border border-ok/30 bg-ok-subtle p-3 text-sm text-ok">
                <p className="flex items-center gap-2 font-medium">
                  <CheckCircle2 className="size-4" /> Importazione applicata.
                </p>
                {batch.report?.applicato ? (
                  <p className="mt-1">
                    {batch.report.applicato.movimenti} movimenti per{" "}
                    {batch.report.applicato.giornate} gg, da {batch.report.applicato.operatore} il{" "}
                    {formatIstante(batch.report.applicato.istante)}.
                  </p>
                ) : null}
                <p className="mt-1 font-mono text-xs">Importazione {batch.id}</p>
              </div>
            ) : (
              <>
                <p className="mt-1 text-sm text-muted-foreground">
                  {batch.confermabile
                    ? "Tutte le righe sono pronte: la conferma aggiunge i movimenti alle tre sezioni."
                    : "La conferma si abilita quando non restano errori né righe da associare."}
                </p>
                <div className="mt-3 flex items-center gap-3">
                  <Button
                    type="button"
                    variant="primary"
                    disabled={!batch.confermabile || conferma.isPending}
                    onClick={() => conferma.mutate(batch)}
                  >
                    {conferma.isPending ? "Applicazione…" : "Conferma importazione"}
                  </Button>
                  {!batch.confermabile ? (
                    <span className="text-warning flex items-center gap-2 text-xs">
                      <AlertTriangle className="size-4" />
                      {errori > 0
                        ? `${errori} errori da correggere nel file`
                        : "Associazioni da completare in Riconciliazione"}
                    </span>
                  ) : null}
                </div>
              </>
            )}
          </div>
        </>
      ) : null}

      {/* Storico */}
      <div className="rounded-xl border border-border bg-card p-5 shadow-subtle">
        <h2 className="text-sm font-semibold">Storico delle importazioni</h2>
        {storico.isLoading ? (
          <LoadingState rows={3} />
        ) : storico.isError ? (
          <ErrorState title="Storico non disponibile" />
        ) : (storico.data?.importazioni ?? []).length === 0 ? (
          <EmptyState title="Nessuna importazione registrata" />
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="py-2">File</th>
                  <th className="py-2">Stato</th>
                  <th className="py-2">Caricato</th>
                  <th className="py-2">Operatore</th>
                  <th className="py-2">Applicato</th>
                  <th className="py-2 text-right">Movimenti</th>
                </tr>
              </thead>
              <tbody>
                {(storico.data?.importazioni ?? []).map((b) => (
                  <tr key={b.id} className="border-t border-border">
                    <td className="py-2">{b.file || "—"}</td>
                    <td className="py-2">{b.stato_etichetta}</td>
                    <td className="whitespace-nowrap py-2">{formatIstante(b.creato_il)}</td>
                    <td className="py-2">{b.operatore ?? "—"}</td>
                    <td className="whitespace-nowrap py-2">{formatIstante(b.applicato_il)}</td>
                    <td className="py-2 text-right">{b.report?.applicato?.movimenti ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
