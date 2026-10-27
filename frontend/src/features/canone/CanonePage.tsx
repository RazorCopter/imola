import { useEffect, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AccessibleBarChart, CHART_PALETTE } from "@/components/AccessibleBarChart";
import { DaysValue } from "@/components/DaysValue";
import { MetricLabel } from "@/components/InfoTooltip";
import { EmptyState, ErrorState, LoadingState } from "@/components/UiState";
import { useSession } from "@/features/auth/session";
import { ApiError, api } from "@/lib/api";
import { canCreateTimesheets, canManageCanone } from "@/lib/permissions";

interface CanoneRow {
  id: string;
  version: number;
  semestre: string;
  periodicita: "TRIMESTRALE" | "SEMESTRALE";
  nome: string;
  pianificato: string;
  riservato: string;
  disponibile: string;
  consuntivato: string;
  residuo: string;
  stato: string;
  sottoattivita_count: number;
}
interface CanoneList {
  results: CanoneRow[];
  default_canone_id: string | null;
  summary: {
    pianificato: string;
    riservato: string;
    disponibile: string;
    consuntivato: string;
    residuo: string;
    sottoattivita: number;
  };
  filters: { semestri: string[]; stati: string[]; domini: string[] };
}
interface TimesheetRow {
  id: string;
  data: string;
  giornate: string;
  descrizione: string;
  utente: string;
  origine: string;
}
interface Subactivity {
  id: string;
  version: number;
  office: string;
  title: string;
  reserved_days: string;
  start_date: string | null;
  end_date: string | null;
  remaining_reserved_days: string;
  redmine_ref: string;
  quarter_estimate_days: string | null;
  forecast_remaining_days: string | null;
  notes: string;
  needs_review: boolean;
  consuntivato: string;
  timesheet_count: number;
  consuntivi: TimesheetRow[];
}
interface Detail {
  id: string;
  version: number;
  name: string;
  semester: string;
  periodicity: "TRIMESTRALE" | "SEMESTRALE";
  total_days: string;
  reserved_days: string;
  available_days: string;
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
  const canConsuntiva = canCreateTimesheets(session);
  const isAdmin = Boolean(session?.is_admin);
  const [semester, setSemester] = useState("");
  const [search, setSearch] = useState("");
  const [state, setState] = useState("");
  const [office, setOffice] = useState("");
  const [appliedFilters, setAppliedFilters] = useState({
    semester: "",
    search: "",
    state: "",
    office: "",
  });
  const [selected, setSelected] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState("");
  const [form, setForm] = useState({
    name: "",
    semester: "",
    periodicity: "SEMESTRALE" as "TRIMESTRALE" | "SEMESTRALE",
    total_days: "",
    target_base_days: "2",
    target_days_per_week: "0",
    start_date: "",
    end_date: "",
  });
  const [subForm, setSubForm] = useState({
    office: "",
    title: "",
    reserved_days: "",
    start_date: "",
    end_date: "",
    quarter_estimate_days: "",
    forecast_remaining_days: "",
    notes: "",
  });
  const [editingSubactivity, setEditingSubactivity] = useState<Subactivity | null>(null);
  const [timesheetActivity, setTimesheetActivity] = useState<string | null>(null);
  const [timesheetForm, setTimesheetForm] = useState({ data: "", giornate: "", descrizione: "" });
  const [editingTimesheet, setEditingTimesheet] = useState<TimesheetRow | null>(null);

  const params = new URLSearchParams({ management: "1" });
  if (appliedFilters.semester) params.set("semester", appliedFilters.semester);
  if (appliedFilters.search) params.set("search", appliedFilters.search);
  if (appliedFilters.state) params.set("state", appliedFilters.state);
  if (appliedFilters.office) params.set("office", appliedFilters.office);
  const index = useQuery({
    queryKey: ["canoni", appliedFilters],
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
      name: detail.data.name,
      semester: detail.data.semester,
      periodicity: detail.data.periodicity,
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
    mutationFn: () => {
      const payload = {
        name: form.name,
        semester: form.semester,
        periodicity: form.periodicity,
        total_days: form.total_days,
      };
      return creating
        ? api.post<Detail>("/canoni", payload)
        : api.patch<Detail>(`/canoni/${canoneId}`, {
            ...payload,
            expected_version: detail.data?.version,
          });
    },
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
    mutationFn: () =>
      editingSubactivity
        ? api.patch<Detail>(`/canoni/${canoneId}/subactivities/${editingSubactivity.id}`, {
            ...subForm,
            expected_version: editingSubactivity.version,
          })
        : api.post<Detail>(`/canoni/${canoneId}/subactivities`, subForm),
    onSuccess: async () => {
      setSubForm({
        office: "",
        title: "",
        reserved_days: "",
        start_date: "",
        end_date: "",
        quarter_estimate_days: "",
        forecast_remaining_days: "",
        notes: "",
      });
      setEditingSubactivity(null);
      await refresh(canoneId);
    },
    onError: (error) => setFormError(message(error)),
  });
  const saveTimesheet = useMutation({
    mutationFn: () =>
      editingTimesheet
        ? api.patch<Detail>(
            `/canoni/${canoneId}/subactivities/${timesheetActivity}/timesheets/${editingTimesheet.id}`,
            timesheetForm,
          )
        : api.post<Detail>(
            `/canoni/${canoneId}/subactivities/${timesheetActivity}/timesheets`,
            timesheetForm,
          ),
    onSuccess: async () => {
      setTimesheetForm({ data: "", giornate: "", descrizione: "" });
      setEditingTimesheet(null);
      await refresh(canoneId);
    },
    onError: (error) => setFormError(message(error)),
  });
  const removeTimesheet = useMutation({
    mutationFn: ({ activityId, entryId }: { activityId: string; entryId: string }) =>
      api.delete<void>(`/canoni/${canoneId}/subactivities/${activityId}/timesheets/${entryId}`),
    onSuccess: async () => refresh(canoneId),
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
    name: `${row.semestre} · ${row.nome}`,
    pianificato: Number(row.pianificato),
    consuntivato: Number(row.consuntivato),
    residuo: Number(row.residuo),
  }));

  return (
    <section className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Organico Allargato</h1>
          <p className="text-sm text-muted-foreground">
            Gestione canoni e attività che ne riservano il monte giornate.
          </p>
        </div>
        {editable && (
          <button
            className={buttonClass}
            onClick={() => {
              setCreating(true);
              setEditing(true);
              setForm({
                name: "",
                semester: "",
                periodicity: "SEMESTRALE",
                total_days: "",
                target_base_days: "2",
                target_days_per_week: "0",
                start_date: "",
                end_date: "",
              });
            }}
          >
            Nuovo canone
          </button>
        )}
      </header>
      <div className="grid gap-3 sm:grid-cols-4">
        {(
          [
            [
              "Monte canoni",
              data.summary.pianificato,
              "Monte giornate complessivo dei canoni visualizzati.",
            ],
            [
              "Riservato attività",
              data.summary.riservato,
              "Giornate assegnate alle attività censite sui canoni visualizzati.",
            ],
            [
              "Disponibile da riservare",
              data.summary.disponibile,
              "Monte dei canoni non ancora assegnato ad attività.",
            ],
          ] satisfies Array<[string, string, string]>
        ).map(([label, value, description]) => (
          <div key={label} className="rounded-lg border bg-card p-4">
            <MetricLabel label={label} description={description} />
            <p className="text-xl font-semibold">
              <DaysValue value={value} />
            </p>
          </div>
        ))}
        <div className="rounded-lg border bg-card p-4">
          <MetricLabel
            label="Attività"
            description="Numero di attività operative censite sui canoni visualizzati."
          />
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
      <h2 className="text-lg font-semibold">Canoni trimestrali e semestrali</h2>
      <div className="flex flex-wrap gap-2">
        <input
          aria-label="Ricerca"
          className={fieldClass}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Cerca codice o titolo"
        />
        <select
          aria-label="Periodo"
          className={fieldClass}
          value={semester}
          onChange={(e) => setSemester(e.target.value)}
        >
          <option value="">Tutti i periodi</option>
          {data.filters.semestri.map((value) => (
            <option key={value}>{value}</option>
          ))}
        </select>
        <select
          aria-label="Dominio"
          className={fieldClass}
          value={office}
          onChange={(e) => setOffice(e.target.value)}
        >
          <option value="">Tutti i domini</option>
          {data.filters.domini.map((value) => (
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
        <button
          className={buttonClass}
          onClick={() => {
            setSelected(null);
            setCreating(false);
            setEditing(false);
            setAppliedFilters({ semester, search: search.trim(), state, office });
          }}
        >
          Applica filtri
        </button>
        <button
          className={buttonClass}
          onClick={() => {
            setSemester("");
            setSearch("");
            setState("");
            setOffice("");
            setSelected(null);
            setCreating(false);
            setEditing(false);
            setAppliedFilters({ semester: "", search: "", state: "", office: "" });
          }}
        >
          Azzera
        </button>
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
                <th className="p-3">Periodo</th>
                <th>Periodicità</th>
                <th>Canone</th>
                <th>Monte</th>
                <th>Riservato</th>
                <th>Disponibile</th>
                <th>Consuntivato</th>
                <th>Stato</th>
                <th>Attività</th>
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
                  <td>{row.periodicita === "TRIMESTRALE" ? "Trimestrale" : "Semestrale"}</td>
                  <td>{row.nome}</td>
                  <td>
                    <DaysValue value={row.pianificato} />
                  </td>
                  <td>
                    <DaysValue value={row.riservato} />
                  </td>
                  <td>
                    <DaysValue value={row.disponibile} />
                  </td>
                  <td>
                    <DaysValue value={row.consuntivato} />
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
                  {creating ? "Nuovo canone" : `${detail.data?.name} · ${detail.data?.semester}`}
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
                  <label className="text-sm">
                    Nome canone
                    <input
                      aria-label="Nome canone"
                      className={`${fieldClass} mt-1 w-full`}
                      placeholder="Es. Organico Allargato"
                      value={form.name}
                      onChange={(e) => setForm({ ...form, name: e.target.value })}
                    />
                  </label>
                  <label className="text-sm">
                    Periodicità
                    <select
                      aria-label="Periodicità"
                      className={`${fieldClass} mt-1 w-full`}
                      value={form.periodicity}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          periodicity: e.target.value as "TRIMESTRALE" | "SEMESTRALE",
                          semester: "",
                        })
                      }
                    >
                      <option value="TRIMESTRALE">Trimestrale</option>
                      <option value="SEMESTRALE">Semestrale</option>
                    </select>
                  </label>
                  <label className="text-sm">
                    Periodo
                    <input
                      aria-label="Periodo del canone"
                      className={`${fieldClass} mt-1 w-full`}
                      placeholder={form.periodicity === "TRIMESTRALE" ? "2026-Q1" : "2026-S1"}
                      value={form.semester}
                      onChange={(e) => setForm({ ...form, semester: e.target.value.toUpperCase() })}
                    />
                  </label>
                  <label className="text-sm">
                    Monte giornate
                    <input
                      aria-label="Monte giornate"
                      className={`${fieldClass} mt-1 w-full`}
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={form.total_days}
                      onChange={(e) => setForm({ ...form, total_days: e.target.value })}
                    />
                  </label>
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
                  <div>
                    <h3 className="text-lg font-semibold">Attività del canone</h3>
                    <p className="text-sm text-muted-foreground">
                      Riservato <DaysValue value={detail.data.reserved_days} /> · disponibile da
                      assegnare <DaysValue value={detail.data.available_days} />
                    </p>
                  </div>
                  {detail.data.subactivities.map((row) => (
                    <div key={row.id} className="space-y-3 rounded border p-3">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <strong>{row.title}</strong>
                          <p className="text-sm text-muted-foreground">
                            Dominio {row.office} · {row.start_date} → {row.end_date} · riservato{" "}
                            <DaysValue value={row.reserved_days} /> · consuntivato{" "}
                            <DaysValue value={row.consuntivato} /> · residuo{" "}
                            <DaysValue value={row.remaining_reserved_days} />
                          </p>
                        </div>
                        <div className="flex gap-2">
                          {canConsuntiva && (
                            <button
                              className={buttonClass}
                              onClick={() => {
                                setTimesheetActivity(row.id);
                                setEditingTimesheet(null);
                                setTimesheetForm({ data: "", giornate: "", descrizione: "" });
                              }}
                            >
                              Consuntiva
                            </button>
                          )}
                          {editable && (
                            <>
                              <button
                                className={buttonClass}
                                onClick={() => {
                                  setEditingSubactivity(row);
                                  setSubForm({
                                    office: row.office,
                                    title: row.title,
                                    reserved_days: row.reserved_days,
                                    start_date: row.start_date ?? "",
                                    end_date: row.end_date ?? "",
                                    quarter_estimate_days: row.quarter_estimate_days ?? "",
                                    forecast_remaining_days: row.forecast_remaining_days ?? "",
                                    notes: row.notes,
                                  });
                                }}
                              >
                                Modifica attività
                              </button>
                              <button className={buttonClass} onClick={() => removeSub.mutate(row)}>
                                Elimina attività
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                      {timesheetActivity === row.id && (
                        <div className="grid gap-2 rounded border border-dashed p-3 sm:grid-cols-4">
                          <input
                            className={fieldClass}
                            aria-label="Data consuntivo"
                            type="date"
                            value={timesheetForm.data}
                            onChange={(e) =>
                              setTimesheetForm({ ...timesheetForm, data: e.target.value })
                            }
                          />
                          <input
                            className={fieldClass}
                            aria-label="Giornate consuntivo"
                            type="number"
                            min="0.01"
                            step="0.01"
                            placeholder="Giornate"
                            value={timesheetForm.giornate}
                            onChange={(e) =>
                              setTimesheetForm({ ...timesheetForm, giornate: e.target.value })
                            }
                          />
                          <input
                            className={fieldClass}
                            aria-label="Descrizione consuntivo"
                            placeholder="Descrizione"
                            value={timesheetForm.descrizione}
                            onChange={(e) =>
                              setTimesheetForm({ ...timesheetForm, descrizione: e.target.value })
                            }
                          />
                          <button className={buttonClass} onClick={() => saveTimesheet.mutate()}>
                            {editingTimesheet ? "Salva rettifica" : "Registra"}
                          </button>
                        </div>
                      )}
                      {row.consuntivi.length > 0 && (
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="text-left">
                                <th>Data</th>
                                <th>Utente</th>
                                <th>Giornate</th>
                                <th>Descrizione</th>
                                {isAdmin && <th>Azioni</th>}
                              </tr>
                            </thead>
                            <tbody>
                              {row.consuntivi.map((entry) => (
                                <tr key={entry.id} className="border-t">
                                  <td>{entry.data}</td>
                                  <td>{entry.utente}</td>
                                  <td>
                                    <DaysValue value={entry.giornate} />
                                  </td>
                                  <td>{entry.descrizione}</td>
                                  {isAdmin && (
                                    <td className="flex gap-2 py-1">
                                      <button
                                        className={buttonClass}
                                        onClick={() => {
                                          setTimesheetActivity(row.id);
                                          setEditingTimesheet(entry);
                                          setTimesheetForm({
                                            data: entry.data,
                                            giornate: entry.giornate,
                                            descrizione: entry.descrizione,
                                          });
                                        }}
                                      >
                                        Modifica
                                      </button>
                                      <button
                                        className={buttonClass}
                                        onClick={() =>
                                          removeTimesheet.mutate({
                                            activityId: row.id,
                                            entryId: entry.id,
                                          })
                                        }
                                      >
                                        Elimina
                                      </button>
                                    </td>
                                  )}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  ))}
                  {editable && (
                    <div className="grid gap-2 rounded border border-dashed p-3 sm:grid-cols-3">
                      {editingSubactivity && (
                        <div className="flex items-center justify-between sm:col-span-3">
                          <strong>Modifica attività</strong>
                          <button
                            className={buttonClass}
                            onClick={() => {
                              setEditingSubactivity(null);
                              setSubForm({
                                office: "",
                                title: "",
                                reserved_days: "",
                                start_date: "",
                                end_date: "",
                                quarter_estimate_days: "",
                                forecast_remaining_days: "",
                                notes: "",
                              });
                            }}
                          >
                            Annulla
                          </button>
                        </div>
                      )}
                      <input
                        className={fieldClass}
                        aria-label="Titolo attività"
                        placeholder="Titolo attività"
                        value={subForm.title}
                        onChange={(e) => setSubForm({ ...subForm, title: e.target.value })}
                      />
                      <select
                        className={fieldClass}
                        aria-label="Gruppo architetturale"
                        value={subForm.office}
                        onChange={(e) => setSubForm({ ...subForm, office: e.target.value })}
                      >
                        <option value="">Gruppo</option>
                        {["EA", "TA", "SA", "CROSS"].map((office) => (
                          <option key={office}>{office}</option>
                        ))}
                      </select>
                      <input
                        className={fieldClass}
                        aria-label="Giornate da riservare"
                        type="number"
                        min="0.01"
                        step="0.01"
                        placeholder="Giornate da riservare"
                        value={subForm.reserved_days}
                        onChange={(e) => setSubForm({ ...subForm, reserved_days: e.target.value })}
                      />
                      <input
                        className={fieldClass}
                        aria-label="Data inizio attività"
                        type="date"
                        value={subForm.start_date}
                        onChange={(e) => setSubForm({ ...subForm, start_date: e.target.value })}
                      />
                      <input
                        className={fieldClass}
                        aria-label="Data fine attività"
                        type="date"
                        value={subForm.end_date}
                        onChange={(e) => setSubForm({ ...subForm, end_date: e.target.value })}
                      />
                      <button className={buttonClass} onClick={() => addSub.mutate()}>
                        {editingSubactivity ? "Salva modifiche" : "Aggiungi attività"}
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
