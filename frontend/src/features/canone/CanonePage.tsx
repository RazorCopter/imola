import { useEffect, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AccessibleBarChart, CHART_PALETTE } from "@/components/AccessibleBarChart";
import { DaysValue } from "@/components/DaysValue";
import { EmptyState, ErrorState, LoadingState } from "@/components/UiState";
import { useSession } from "@/features/auth/session";
import { ApiError, api } from "@/lib/api";
import { canManageCanone } from "@/lib/permissions";

interface CanoneRow {
  id: string;
  version: number;
  semestre: string;
  progetto_id: string;
  progetto_codice: string;
  progetto_titolo: string;
  fornitore: string | null;
  pianificato: string;
  consuntivato: string;
  residuo: string;
  stato: string;
  sottoattivita_count: number;
}
interface CanoneList {
  results: CanoneRow[];
  default_canone_id: string | null;
  summary: { pianificato: string; consuntivato: string; residuo: string; sottoattivita: number };
  filters: { semestri: string[]; stati: string[] };
}
interface Subactivity {
  id: string;
  version: number;
  office: string;
  title: string;
  redmine_ref: string;
  quarter_estimate_days: string | null;
  forecast_remaining_days: string | null;
  notes: string;
  needs_review: boolean;
  consuntivato: string;
  timesheet_count: number;
}
interface Detail {
  id: string;
  version: number;
  project_id: string;
  progetto_codice: string;
  progetto_titolo: string;
  semester: string;
  total_days: string;
  target_base_days: string;
  target_days_per_week: string;
  cap_at_total: boolean;
  start_date: string | null;
  end_date: string | null;
  status: { consuntivato: string; residuo?: string; forecast: string };
  subactivities: Subactivity[];
}

const fieldClass = "h-9 rounded-md border border-input bg-background px-3 text-sm";
const buttonClass =
  "rounded-md border border-input px-3 py-2 text-sm hover:bg-muted disabled:opacity-50";

function message(error: unknown): string {
  if (!(error instanceof ApiError)) return "Operazione non riuscita.";
  if (error.status === 409) return "I dati sono cambiati: ricarica e riprova.";
  if (error.status === 428) return "Versione mancante: ricarica il dettaglio.";
  if (error.status === 403) return "Non sei autorizzato a modificare l’Organico Allargato.";
  return error.message;
}

export function CanonePage() {
  const queryClient = useQueryClient();
  const { session } = useSession();
  const editable = canManageCanone(session);
  const [semester, setSemester] = useState("");
  const [search, setSearch] = useState("");
  const [state, setState] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState("");
  const [form, setForm] = useState({
    project_id: "",
    semester: "",
    total_days: "",
    target_base_days: "2",
    target_days_per_week: "0",
    start_date: "",
    end_date: "",
  });
  const [subForm, setSubForm] = useState({
    office: "",
    title: "",
    quarter_estimate_days: "",
    forecast_remaining_days: "",
    notes: "",
  });

  const params = new URLSearchParams({ management: "1" });
  if (semester) params.set("semester", semester);
  if (search) params.set("search", search);
  if (state) params.set("state", state);
  const index = useQuery({
    queryKey: ["canoni", semester, search, state],
    queryFn: () => api.get<CanoneList>(`/canoni${params.size ? `?${params}` : ""}`),
    placeholderData: keepPreviousData,
  });
  const canoneId = selected ?? index.data?.default_canone_id ?? "";
  const detail = useQuery({
    queryKey: ["canone", canoneId],
    queryFn: () => api.get<Detail>(`/canoni/${canoneId}`),
    enabled: Boolean(canoneId),
  });

  useEffect(() => {
    if (!detail.data || editing) return;
    setForm({
      project_id: detail.data.project_id,
      semester: detail.data.semester,
      total_days: detail.data.total_days,
      target_base_days: detail.data.target_base_days,
      target_days_per_week: detail.data.target_days_per_week,
      start_date: detail.data.start_date ?? "",
      end_date: detail.data.end_date ?? "",
    });
  }, [detail.data, editing]);

  async function refresh(id?: string) {
    await queryClient.invalidateQueries({ queryKey: ["canoni"] });
    await queryClient.invalidateQueries({ queryKey: ["canone"] });
    if (id) setSelected(id);
  }
  const save = useMutation({
    mutationFn: () =>
      creating
        ? api.post<Detail>("/canoni", form)
        : api.patch<Detail>(`/canoni/${canoneId}`, {
            ...form,
            expected_version: detail.data?.version,
          }),
    onSuccess: async (data) => {
      setCreating(false);
      setEditing(false);
      setFormError("");
      await refresh(data.id);
    },
    onError: (error) => setFormError(message(error)),
  });
  const remove = useMutation({
    mutationFn: () =>
      api.delete<void>(`/canoni/${canoneId}`, { body: { expected_version: detail.data?.version } }),
    onSuccess: async () => {
      setSelected(null);
      await refresh();
    },
    onError: (error) => setFormError(message(error)),
  });
  const addSub = useMutation({
    mutationFn: () => api.post<Detail>(`/canoni/${canoneId}/subactivities`, subForm),
    onSuccess: async () => {
      setSubForm({
        office: "",
        title: "",
        quarter_estimate_days: "",
        forecast_remaining_days: "",
        notes: "",
      });
      await refresh(canoneId);
    },
    onError: (error) => setFormError(message(error)),
  });
  const removeSub = useMutation({
    mutationFn: (row: Subactivity) =>
      api.delete<Detail>(`/canoni/${canoneId}/subactivities/${row.id}`, {
        body: { expected_version: row.version },
      }),
    onSuccess: async () => refresh(canoneId),
    onError: (error) => setFormError(message(error)),
  });

  if (index.isLoading) return <LoadingState />;
  if (index.isError) return <ErrorState title="Impossibile caricare l’Organico Allargato" />;
  const data = index.data!;
  const chart = data.results.map((row) => ({
    name: `${row.semestre} · ${row.progetto_codice}`,
    pianificato: Number(row.pianificato),
    consuntivato: Number(row.consuntivato),
    residuo: Number(row.residuo),
  }));

  return (
    <section className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Organico Allargato</h1>
          <p className="text-sm text-muted-foreground">Voci, consuntivi e forecast correlati.</p>
        </div>
        {editable && (
          <button
            className={buttonClass}
            onClick={() => {
              setCreating(true);
              setEditing(true);
              setForm({
                project_id: "",
                semester: "",
                total_days: "",
                target_base_days: "2",
                target_days_per_week: "0",
                start_date: "",
                end_date: "",
              });
            }}
          >
            Crea
          </button>
        )}
      </header>
      <div className="grid gap-3 sm:grid-cols-4">
        {[
          ["Pianificato", data.summary.pianificato],
          ["Consuntivato", data.summary.consuntivato],
          ["Residuo", data.summary.residuo],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg border bg-card p-4">
            <p className="text-sm text-muted-foreground">{label}</p>
            <p className="text-xl font-semibold">
              <DaysValue value={value as string} />
            </p>
          </div>
        ))}
        <div className="rounded-lg border bg-card p-4">
          <p className="text-sm text-muted-foreground">Sottoattività</p>
          <p className="text-xl font-semibold">{data.summary.sottoattivita}</p>
        </div>
      </div>
      <div
        className="h-72 rounded-lg border bg-card p-4"
        aria-label="Confronto pianificato, consuntivato e residuo per voce"
      >
        {chart.length ? (
          <AccessibleBarChart
            data={chart}
            xKey="name"
            unit="days"
            series={[
              { key: "pianificato", label: "Pianificato", color: CHART_PALETTE.slate },
              { key: "consuntivato", label: "Consuntivato", color: CHART_PALETTE.blue },
              { key: "residuo", label: "Residuo", color: CHART_PALETTE.green },
            ]}
          />
        ) : (
          <p className="text-sm text-muted-foreground">Nessun dato per il grafico.</p>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <input
          aria-label="Ricerca"
          className={fieldClass}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Cerca codice o titolo"
        />
        <select
          aria-label="Semestre"
          className={fieldClass}
          value={semester}
          onChange={(e) => setSemester(e.target.value)}
        >
          <option value="">Tutti i semestri</option>
          {data.filters.semestri.map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
        <select
          aria-label="Stato"
          className={fieldClass}
          value={state}
          onChange={(e) => setState(e.target.value)}
        >
          <option value="">Tutti gli stati</option>
          {data.filters.stati.map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
      </div>
      {!data.results.length ? (
        <EmptyState
          title="Nessuna voce trovata"
          detail="Modifica i filtri o crea una nuova voce."
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50 text-left">
                <th className="p-3">Semestre</th>
                <th>Progetto</th>
                <th>Pianificato</th>
                <th>Consuntivato</th>
                <th>Residuo</th>
                <th>Stato</th>
                <th>Sottoattività</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((row) => (
                <tr
                  key={row.id}
                  tabIndex={0}
                  aria-selected={canoneId === row.id}
                  className="cursor-pointer border-b hover:bg-muted/50 focus:bg-muted"
                  onClick={() => setSelected(row.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelected(row.id);
                    }
                  }}
                >
                  <td className="p-3">{row.semestre}</td>
                  <td>
                    {row.progetto_codice} · {row.progetto_titolo}
                  </td>
                  <td>
                    <DaysValue value={row.pianificato} />
                  </td>
                  <td>
                    <DaysValue value={row.consuntivato} />
                  </td>
                  <td>
                    <DaysValue value={row.residuo} />
                  </td>
                  <td>{row.stato}</td>
                  <td>{row.sottoattivita_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {(creating || canoneId) && (
        <aside
          className="space-y-4 rounded-lg border bg-card p-4"
          aria-label="Dettaglio Organico Allargato"
        >
          {!creating && detail.isLoading ? (
            <LoadingState />
          ) : (
            <>
              <div className="flex justify-between">
                <h2 className="font-semibold">
                  {creating
                    ? "Nuova voce"
                    : `${detail.data?.progetto_codice} · ${detail.data?.semester}`}
                </h2>
                {editable && !creating && (
                  <div className="flex gap-2">
                    <button className={buttonClass} onClick={() => setEditing(!editing)}>
                      {editing ? "Annulla" : "Modifica"}
                    </button>
                    <button className={buttonClass} onClick={() => remove.mutate()}>
                      Elimina
                    </button>
                  </div>
                )}
              </div>
              {(editing || creating) && (
                <div className="grid gap-3 sm:grid-cols-3">
                  {(
                    [
                      ["project_id", "ID progetto"],
                      ["semester", "Semestre"],
                      ["total_days", "Giornate"],
                      ["target_base_days", "Base target"],
                      ["target_days_per_week", "Giornate/settimana"],
                      ["start_date", "Data inizio"],
                      ["end_date", "Data fine"],
                    ] as const
                  ).map(([key, label]) => (
                    <label key={key} className="text-sm">
                      {label}
                      <input
                        className={`${fieldClass} mt-1 w-full`}
                        type={key.includes("date") ? "date" : "text"}
                        value={form[key]}
                        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                      />
                    </label>
                  ))}
                  <div className="sm:col-span-3">
                    <button
                      className={buttonClass}
                      disabled={save.isPending}
                      onClick={() => save.mutate()}
                    >
                      Salva
                    </button>
                  </div>
                </div>
              )}
              {formError && (
                <p role="alert" className="text-destructive text-sm">
                  {formError}
                </p>
              )}
              {!creating && detail.data && (
                <div className="space-y-3">
                  <h3 className="font-medium">Sottoattività e consuntivi</h3>
                  {detail.data.subactivities.map((row) => (
                    <div
                      key={row.id}
                      className="flex flex-wrap items-center justify-between gap-2 rounded border p-3"
                    >
                      <div>
                        <strong>{row.title}</strong>
                        <p className="text-sm text-muted-foreground">
                          {row.office || "Senza ufficio"} · consuntivato{" "}
                          <DaysValue value={row.consuntivato} /> · {row.timesheet_count} movimenti
                        </p>
                      </div>
                      {editable && (
                        <button className={buttonClass} onClick={() => removeSub.mutate(row)}>
                          Elimina
                        </button>
                      )}
                    </div>
                  ))}
                  {editable && (
                    <div className="grid gap-2 sm:grid-cols-3">
                      <input
                        className={fieldClass}
                        placeholder="Titolo sottoattività"
                        value={subForm.title}
                        onChange={(e) => setSubForm({ ...subForm, title: e.target.value })}
                      />
                      <select
                        className={fieldClass}
                        value={subForm.office}
                        onChange={(e) => setSubForm({ ...subForm, office: e.target.value })}
                      >
                        <option value="">Ufficio</option>
                        {["EA", "SA", "TA", "CROSS"].map((office) => (
                          <option key={office}>{office}</option>
                        ))}
                      </select>
                      <button className={buttonClass} onClick={() => addSub.mutate()}>
                        Aggiungi sottoattività
                      </button>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </aside>
      )}
    </section>
  );
}
