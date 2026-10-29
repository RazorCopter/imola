import { PageHeader } from "@/components/PageHeader";
import { Button, Input, Select } from "@/components/Controls";
import { useEffect, useMemo, useState, useRef } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AccessibleBarChart, CHART_PALETTE } from "@/components/AccessibleBarChart";
import { ConfirmActionDialog } from "@/components/ConfirmActionDialog";
import { DaysValue } from "@/components/DaysValue";
import { KpiCard } from "@/components/KpiCard";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState, ErrorState, LoadingState } from "@/components/UiState";
import { useSession } from "@/features/auth/session";
import { ApiError, api } from "@/lib/api";
import { formatDays, formatPercent, parseDays } from "@/lib/format";
import { canCreateTimesheets, canEditTimesheets, canManageCanone } from "@/lib/permissions";

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
  stato: "IN_CORSO" | "CHIUSO";
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
  status: {
    consuntivato: string;
    residuo?: string;
    target_alla_data: string;
    delta: string;
    forecast: string;
    percentuale_forecast: string;
    proiezione: string;
    giornate_non_usate_previste: string;
  };
  subactivities: Subactivity[];
}

function ActivityProgress({ activity }: { activity: Subactivity }) {
  const planned = parseDays(activity.reserved_days);
  const consumed = parseDays(activity.consuntivato);
  // Visual utilisation only: accounting totals and remaining days still come from the API.
  const ratio = planned !== null && planned > 0 && consumed !== null ? consumed / planned : null;
  const percent = ratio !== null && Number.isFinite(ratio) ? ratio * 100 : null;
  const exceeded = planned !== null && consumed !== null && consumed > planned;
  const width = percent === null ? 0 : Math.min(100, Math.max(0, percent));
  const description = `${formatDays(activity.consuntivato)} consuntivate su ${formatDays(activity.reserved_days)} previste`;

  return (
    <span className="block w-full space-y-1">
      <span className="flex items-center justify-between gap-3 text-xs tabular-nums">
        <span className="text-muted-foreground">
          Consuntivate <DaysValue value={activity.consuntivato} suffix={false} /> /{" "}
          <DaysValue value={activity.reserved_days} />
        </span>
        <span className={exceeded ? "font-semibold text-danger" : "font-medium"}>
          {percent === null
            ? planned === 0
              ? "Senza previsione"
              : "Non disponibile"
            : formatPercent(percent)}
        </span>
      </span>
      <span
        role={percent === null ? "img" : "progressbar"}
        aria-label={`${activity.title}: ${description}${percent === null ? ". Avanzamento non calcolabile" : ""}`}
        aria-valuemin={percent === null ? undefined : 0}
        aria-valuemax={percent === null ? undefined : 100}
        aria-valuenow={percent === null ? undefined : width}
        aria-valuetext={percent === null ? undefined : `${formatPercent(percent)}. ${description}`}
        className="block h-1.5 overflow-hidden rounded-full bg-muted"
        title={description}
      >
        <span
          className={`block h-full rounded-full ${exceeded ? "bg-danger" : percent !== null && percent >= 100 ? "bg-ok" : "bg-accent"}`}
          style={{ width: `${width}%` }}
        />
      </span>
    </span>
  );
}

const domainCardClasses: Record<string, string> = {
  TA: "border-red-300/70 bg-gradient-to-r from-red-100/90 via-red-50/40 to-transparent dark:border-red-800/60 dark:from-red-950/75 dark:via-red-950/25",
  EA: "border-emerald-300/70 bg-gradient-to-r from-emerald-100/90 via-emerald-50/40 to-transparent dark:border-emerald-800/60 dark:from-emerald-950/75 dark:via-emerald-950/25",
  SA: "border-yellow-300/70 bg-gradient-to-r from-yellow-100/90 via-yellow-50/40 to-transparent dark:border-yellow-800/60 dark:from-yellow-950/75 dark:via-yellow-950/25",
};

const fieldClass = "h-9 rounded-md border border-input bg-background px-3 text-sm";
const buttonClass =
  "rounded-md border border-input px-3 py-2 text-sm hover:bg-muted disabled:opacity-50";
const dangerButtonClass =
  "rounded-md border border-red-700 bg-red-700 px-3 py-2 text-sm font-semibold text-white hover:bg-red-800 disabled:opacity-50";

function message(error: unknown): string {
  if (!(error instanceof ApiError)) return "Operazione non riuscita.";
  if (error.status === 409) return "I dati sono cambiati: ricarica e riprova.";
  if (error.status === 428) return "Versione mancante: ricarica il dettaglio.";
  if (error.status === 403) return "Non sei autorizzato a modificare l’Organico Allargato.";
  return error.message;
}

function projectionStatus(value: string): string {
  if (value === "Sotto-utilizzo previsto") return "CANONE_SOTTO_UTILIZZO";
  if (value === "Sovra-utilizzo previsto") return "CANONE_SOVRA_UTILIZZO";
  return "CANONE_IN_LINEA";
}

export function CanonePage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { session } = useSession();
  const editable = canManageCanone(session);
  const canConsuntiva = canCreateTimesheets(session);
  const canEditConsuntivi = canEditTimesheets(session);
  const deleteOpener = useRef<HTMLButtonElement | null>(null);
  const [deleteConfirmation, setDeleteConfirmation] = useState<{
    title: string;
    description: string;
    confirm: () => void;
  } | null>(null);
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
  const [filterRevision, setFilterRevision] = useState(0);
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
    redmine_ref: "",
    reserved_days: "",
    start_date: "",
    end_date: "",
    quarter_estimate_days: "",
    forecast_remaining_days: "",
    notes: "",
  });
  const [editingSubactivity, setEditingSubactivity] = useState<Subactivity | null>(null);
  const [creatingActivity, setCreatingActivity] = useState(false);
  const [activityTab, setActivityTab] = useState("Panoramica");
  const [selectedActivity, setSelectedActivity] = useState<string | null>(null);
  const [activityDomain, setActivityDomain] = useState("");
  const [timesheetActivity, setTimesheetActivity] = useState<string | null>(null);
  const [timesheetForm, setTimesheetForm] = useState({ data: "", giornate: "", descrizione: "" });
  const [editingTimesheet, setEditingTimesheet] = useState<TimesheetRow | null>(null);

  const params = new URLSearchParams({ management: "1" });
  if (appliedFilters.semester) params.set("semester", appliedFilters.semester);
  if (appliedFilters.search) params.set("search", appliedFilters.search);
  if (appliedFilters.state) params.set("state", appliedFilters.state);
  if (appliedFilters.office) params.set("office", appliedFilters.office);
  const index = useQuery({
    queryKey: ["canoni", appliedFilters, filterRevision],
    queryFn: () => api.get<CanoneList>(`/canoni${params.size ? `?${params}` : ""}`),
    placeholderData: keepPreviousData,
  });
  const activeResults = index.data?.results ?? [];
  const selectedCanoneExists = activeResults.some((row) => row.id === selected);
  const defaultCanoneExists = activeResults.some((row) => row.id === index.data?.default_canone_id);
  const canoneId =
    (selected && selectedCanoneExists ? selected : null) ??
    (defaultCanoneExists ? index.data?.default_canone_id : null) ??
    activeResults[0]?.id ??
    "";

  const detailParams = new URLSearchParams();
  if (appliedFilters.office) detailParams.set("office", appliedFilters.office);
  if (appliedFilters.search) detailParams.set("search", appliedFilters.search);
  const detailQuery = detailParams.size ? `?${detailParams}` : "";

  const detail = useQuery({
    queryKey: ["canone", canoneId, appliedFilters.office, appliedFilters.search, filterRevision],
    queryFn: () => api.get<Detail>(`/canoni/${canoneId}${detailQuery}`),
    enabled: Boolean(canoneId),
    placeholderData: keepPreviousData,
  });

  const filteredSubactivities = useMemo(() => {
    if (!detail.data?.subactivities) return [];
    return detail.data.subactivities.filter((row) => {
      if (
        appliedFilters.office &&
        row.office.trim().toUpperCase() !== appliedFilters.office.trim().toUpperCase()
      ) {
        return false;
      }
      if (appliedFilters.search) {
        const needle = appliedFilters.search.toLowerCase();
        const matchTitle = (row.title || "").toLowerCase().includes(needle);
        const matchOffice = (row.office || "").toLowerCase().includes(needle);
        const matchNotes = (row.notes || "").toLowerCase().includes(needle);
        const matchRedmine = (row.redmine_ref || "").toLowerCase().includes(needle);
        if (!matchTitle && !matchOffice && !matchNotes && !matchRedmine) {
          return false;
        }
      }
      return true;
    });
  }, [detail.data?.subactivities, appliedFilters.office, appliedFilters.search]);
  const visibleSubactivities = useMemo(
    () =>
      filteredSubactivities.filter(
        (row) => !activityDomain || row.office.trim().toUpperCase() === activityDomain,
      ),
    [filteredSubactivities, activityDomain],
  );
  const detailIsCurrent = detail.data?.id === canoneId;
  useEffect(() => {
    setSelectedActivity(null);
    setActivityDomain("");
    setCreatingActivity(false);
    setTimesheetActivity(null);
    setEditingTimesheet(null);
    setEditingSubactivity(null);
    setActivityTab("Panoramica");
    setFormError("");
  }, [canoneId]);

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
        redmine_ref: "",
        reserved_days: "",
        start_date: "",
        end_date: "",
        quarter_estimate_days: "",
        forecast_remaining_days: "",
        notes: "",
      });
      setEditingSubactivity(null);
      setCreatingActivity(false);
      setFormError("");
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
      setTimesheetActivity(null);
      setFormError("");
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
    onSuccess: async () => {
      setSelectedActivity(null);
      await refresh(canoneId);
    },
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
      <ConfirmActionDialog
        open={Boolean(deleteConfirmation)}
        title={deleteConfirmation?.title ?? "Conferma eliminazione"}
        description={deleteConfirmation?.description ?? ""}
        pending={remove.isPending || removeSub.isPending || removeTimesheet.isPending}
        error={formError}
        onConfirm={() => deleteConfirmation?.confirm()}
        onOpenChange={(open) => {
          if (!open) setDeleteConfirmation(null);
        }}
        returnFocusTo={deleteOpener.current}
      />
      <PageHeader
        eyebrow="Gestione · Capacità"
        title={t("canone.title")}
        description={t("canone.description")}
        actions={
          <>
            {editable && (
              <Button
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
              </Button>
            )}
          </>
        }
      />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <KpiCard
          label={t("canone.plannedTotal")}
          value={<DaysValue value={data.summary.pianificato} />}
          tooltip={t("canone.plannedTotalTooltip")}
        />
        <KpiCard
          label={t("canone.reservedActivities")}
          value={<DaysValue value={data.summary.riservato} />}
          tooltip={t("canone.reservedActivitiesTooltip")}
        />
        <KpiCard
          label={t("canone.availableToReserve")}
          value={<DaysValue value={data.summary.disponibile} />}
          tooltip={t("canone.availableToReserveTooltip")}
          tone="ok"
        />
        <KpiCard
          label="Consumo del monte"
          value={
            Number(data.summary.pianificato) > 0
              ? formatPercent(
                  (Number(data.summary.consuntivato) / Number(data.summary.pianificato)) * 100,
                )
              : "Non calcolabile"
          }
          hint={`${formatDays(data.summary.consuntivato)} su ${formatDays(data.summary.pianificato)}`}
          tooltip="Giornate consuntivate divise per il monte complessivo dei canoni visualizzati."
        />
        <KpiCard
          label={t("canone.activities")}
          value={data.summary.sottoattivita}
          tooltip={t("canone.activitiesTooltip")}
        />
      </div>
      <div
        className="h-48 rounded-xl border bg-card p-4"
        aria-label="Confronto pianificato, consuntivato e residuo per voce"
      >
        {chart.length ? (
          <div className="mx-auto h-full max-w-4xl">
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
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Nessun dato per il grafico.</p>
        )}
      </div>
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Canoni trimestrali e semestrali</h2>
        <p className="text-sm text-muted-foreground">
          Seleziona un canone per consultare capacità e attività.
        </p>
      </div>
      <div className="flex flex-wrap gap-2 rounded-xl border border-border bg-card p-3">
        <label className="sr-only" htmlFor="canone-search">
          {t("canone.search")}
        </label>
        <Input
          id="canone-search"
          aria-label={t("canone.search")}
          className={fieldClass}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Cerca codice o titolo"
        />
        <label className="sr-only" htmlFor="canone-period-filter">
          {t("canone.period")}
        </label>
        <Select
          id="canone-period-filter"
          aria-label={t("canone.period")}
          className={fieldClass}
          value={semester}
          onChange={(e) => setSemester(e.target.value)}
        >
          <option value="">Tutti i periodi</option>
          {data.filters.semestri.map((value) => (
            <option key={value}>{value}</option>
          ))}
        </Select>
        <label className="sr-only" htmlFor="canone-domain-filter">
          {t("canone.domain")}
        </label>
        <Select
          id="canone-domain-filter"
          aria-label={t("canone.domain")}
          className={fieldClass}
          value={office}
          onChange={(e) => setOffice(e.target.value)}
        >
          <option value="">Tutti i domini</option>
          {data.filters.domini.map((value) => (
            <option key={value}>{value}</option>
          ))}
        </Select>
        <label className="sr-only" htmlFor="canone-state-filter">
          {t("canone.state")}
        </label>
        <Select
          id="canone-state-filter"
          aria-label={t("canone.state")}
          className={fieldClass}
          value={state}
          onChange={(e) => setState(e.target.value)}
        >
          <option value="">Tutti gli stati</option>
          {data.filters.stati.map((value) => (
            <option key={value}>{value}</option>
          ))}
        </Select>
        <Button
          className={buttonClass}
          onClick={() => {
            setSelected(null);
            setSelectedActivity(null);
            setTimesheetActivity(null);
            setEditingTimesheet(null);
            setEditingSubactivity(null);
            setCreating(false);
            setEditing(false);
            setAppliedFilters({ semester, search: search.trim(), state, office });
            setFilterRevision((value) => value + 1);
          }}
        >
          {t("canone.applyFilters")}
        </Button>
        <Button
          className={buttonClass}
          onClick={() => {
            setSemester("");
            setSearch("");
            setState("");
            setOffice("");
            setSelected(null);
            setSelectedActivity(null);
            setTimesheetActivity(null);
            setEditingTimesheet(null);
            setEditingSubactivity(null);
            setCreating(false);
            setEditing(false);
            setAppliedFilters({ semester: "", search: "", state: "", office: "" });
            setFilterRevision((value) => value + 1);
          }}
        >
          {t("canone.resetFilters")}
        </Button>
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
                  <td>
                    <StatusBadge status={row.stato} />
                  </td>
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
          {!creating && detail.isError ? (
            <ErrorState
              title="Impossibile caricare il canone"
              action={
                <Button variant="secondary" onClick={() => void detail.refetch()}>
                  Riprova
                </Button>
              }
            />
          ) : !creating && (detail.isLoading || !detailIsCurrent) ? (
            <LoadingState />
          ) : (
            <>
              <div className="flex justify-between">
                <h2 className="font-semibold">
                  {creating ? "Nuovo canone" : `${detail.data?.name} · ${detail.data?.semester}`}
                </h2>
                {editable && !creating && detailIsCurrent && (
                  <div className="flex gap-2">
                    <Button className={buttonClass} onClick={() => setEditing(!editing)}>
                      {editing ? "Annulla" : "Modifica"}
                    </Button>
                    <Button
                      className={buttonClass}
                      disabled={remove.isPending}
                      onClick={(event) => {
                        deleteOpener.current = event.currentTarget;
                        setFormError("");
                        setDeleteConfirmation({
                          title: "Elimina canone",
                          description: `Confermi l'eliminazione di ${detail.data?.name}? L'operazione non pu\u00f2 essere annullata.`,
                          confirm: () =>
                            remove.mutate(undefined, {
                              onSuccess: () => setDeleteConfirmation(null),
                            }),
                        });
                      }}
                    >
                      Elimina
                    </Button>
                  </div>
                )}
              </div>
              {(editing || creating) && (
                <div className="grid gap-3 sm:grid-cols-3">
                  <label className="text-sm">
                    Nome canone
                    <Input
                      aria-label="Nome canone"
                      className={`${fieldClass} mt-1 w-full`}
                      placeholder="Es. Organico Allargato"
                      value={form.name}
                      onChange={(e) => setForm({ ...form, name: e.target.value })}
                    />
                  </label>
                  <label className="text-sm">
                    Periodicità
                    <Select
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
                    </Select>
                  </label>
                  <label className="text-sm">
                    Periodo
                    <Input
                      aria-label="Periodo del canone"
                      className={`${fieldClass} mt-1 w-full`}
                      placeholder={form.periodicity === "TRIMESTRALE" ? "2026-Q1" : "2026-S1"}
                      value={form.semester}
                      onChange={(e) => setForm({ ...form, semester: e.target.value.toUpperCase() })}
                    />
                  </label>
                  <label className="text-sm">
                    Monte giornate
                    <Input
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
                    <Button
                      className={buttonClass}
                      disabled={save.isPending}
                      onClick={() => save.mutate()}
                    >
                      Salva
                    </Button>
                  </div>
                </div>
              )}
              {formError && (
                <p role="alert" className="text-sm text-destructive">
                  {formError}
                </p>
              )}
              {!creating && detail.data && (
                <div className="space-y-3">
                  <div className="grid gap-3 sm:grid-cols-3">
                    <KpiCard
                      label={t("canone.consumed")}
                      value={<DaysValue value={detail.data.status.consuntivato} />}
                      tooltip={t("canone.consumedTooltip")}
                    />
                    <KpiCard
                      label={t("canone.forecast")}
                      value={<DaysValue value={detail.data.status.forecast} />}
                      hint={`${detail.data.status.percentuale_forecast}%`}
                      tone={
                        detail.data.status.proiezione === "Sovra-utilizzo previsto"
                          ? "danger"
                          : detail.data.status.proiezione === "Sotto-utilizzo previsto"
                            ? "warn"
                            : "ok"
                      }
                      tooltip={t("canone.forecastTooltip")}
                      action={
                        <StatusBadge status={projectionStatus(detail.data.status.proiezione)} />
                      }
                    />
                    <KpiCard
                      label={t("canone.unusedForecast")}
                      value={<DaysValue value={detail.data.status.giornate_non_usate_previste} />}
                      tooltip={t("canone.unusedForecastTooltip")}
                    />
                  </div>
                  {detail.isFetching && (
                    <p className="text-xs text-muted-foreground" role="status">
                      {t("canone.updatingDetail")}
                    </p>
                  )}
                  <div>
                    <h3 className="text-lg font-semibold">Attività del canone</h3>
                    <p className="text-sm text-muted-foreground">
                      Riservato <DaysValue value={detail.data.reserved_days} /> · disponibile da
                      assegnare <DaysValue value={detail.data.available_days} />
                      {appliedFilters.office && (
                        <span>
                          {" "}
                          · Filtro dominio: <strong>{appliedFilters.office}</strong> (
                          {filteredSubactivities.length} attività)
                        </span>
                      )}
                    </p>
                  </div>
                  {!selectedActivity && (
                    <div
                      className="flex flex-wrap items-center gap-2"
                      role="group"
                      aria-label="Filtro rapido dominio attività"
                    >
                      <span className="mr-1 text-sm font-medium">Dominio:</span>
                      {(
                        [
                          ["", "Tutti"],
                          ["TA", "TA"],
                          ["EA", "EA"],
                          ["SA", "SA"],
                          ["CROSS", "CROSS"],
                        ] as const
                      ).map(([value, label]) => (
                        <Button
                          key={label}
                          type="button"
                          aria-pressed={activityDomain === value}
                          onClick={() => setActivityDomain(value)}
                          className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${activityDomain === value ? "border-accent bg-accent text-accent-foreground" : "border-border bg-card text-muted-foreground hover:bg-muted"}`}
                        >
                          {label}
                        </Button>
                      ))}
                      <span className="ml-1 text-xs text-muted-foreground" role="status">
                        {visibleSubactivities.length} / {filteredSubactivities.length} attività
                      </span>
                    </div>
                  )}
                  {visibleSubactivities.length === 0 ? (
                    <p className="rounded border border-dashed p-4 text-center text-sm text-muted-foreground">
                      Nessuna attività trovata per i filtri selezionati.
                    </p>
                  ) : (
                    visibleSubactivities
                      .filter((row) => !selectedActivity || row.id === selectedActivity)
                      .map((row) => (
                        <div
                          key={row.id}
                          className={
                            selectedActivity
                              ? "space-y-3 rounded border p-3"
                              : `rounded border p-2 ${domainCardClasses[row.office.trim().toUpperCase()] ?? "bg-card"}`
                          }
                        >
                          {!selectedActivity ? (
                            <Button
                              className="grid w-full min-w-0 justify-stretch gap-x-5 gap-y-2 rounded px-1 py-0.5 text-left hover:bg-muted/50 focus-visible:outline focus-visible:outline-2 lg:grid-cols-[minmax(0,1fr)_18rem]"
                              onClick={() => {
                                setSelectedActivity(row.id);
                                setActivityTab("Panoramica");
                                setFormError("");
                              }}
                            >
                              <span className="min-w-0">
                                <span className="flex flex-wrap items-center gap-2">
                                  <strong className="text-sm leading-snug">{row.title}</strong>
                                  <StatusBadge
                                    status={
                                      row.stato ??
                                      (Number(row.consuntivato) < Number(row.reserved_days)
                                        ? "IN_CORSO"
                                        : "CHIUSO")
                                    }
                                  />
                                </span>
                                <span className="mt-0.5 block text-xs text-muted-foreground">
                                  Dominio {row.office} · residuo{" "}
                                  <DaysValue value={row.remaining_reserved_days} />
                                </span>
                              </span>
                              <ActivityProgress activity={row} />
                            </Button>
                          ) : (
                            <>
                              <Button
                                className={buttonClass}
                                onClick={() => {
                                  setSelectedActivity(null);
                                  setEditingSubactivity(null);
                                  setTimesheetActivity(null);
                                  setEditingTimesheet(null);
                                  setFormError("");
                                }}
                              >
                                ← Tutte le attività
                              </Button>
                              <div className="flex flex-wrap items-center gap-2">
                                <h3 className="text-lg font-semibold">{row.title}</h3>
                                <StatusBadge
                                  status={
                                    row.stato ??
                                    (Number(row.consuntivato) < Number(row.reserved_days)
                                      ? "IN_CORSO"
                                      : "CHIUSO")
                                  }
                                />
                              </div>
                              <div className="max-w-md">
                                <ActivityProgress activity={row} />
                              </div>
                              <Tabs.Root value={activityTab} onValueChange={setActivityTab}>
                                <Tabs.List
                                  aria-label="Dettaglio attività"
                                  className="flex gap-4 border-b"
                                >
                                  {["Panoramica", "Consuntivi"].map((tab) => (
                                    <Tabs.Trigger
                                      key={tab}
                                      value={tab}
                                      className="border-b-2 border-transparent px-2 py-2 text-sm data-[state=active]:border-primary data-[state=active]:font-semibold"
                                    >
                                      {tab}
                                    </Tabs.Trigger>
                                  ))}
                                </Tabs.List>
                                <Tabs.Content value="Panoramica" className="space-y-3 pt-4">
                                  <p className="text-sm text-muted-foreground">
                                    Dominio {row.office} · {row.start_date || "—"} →{" "}
                                    {row.end_date || "—"}
                                  </p>
                                  <div className="grid gap-3 sm:grid-cols-3">
                                    <KpiCard
                                      label="Riservato"
                                      value={<DaysValue value={row.reserved_days} />}
                                    />
                                    <KpiCard
                                      label="Consuntivato"
                                      value={<DaysValue value={row.consuntivato} />}
                                    />
                                    <KpiCard
                                      label="Residuo"
                                      value={<DaysValue value={row.remaining_reserved_days} />}
                                    />
                                  </div>
                                  <p className="text-sm">Redmine: {row.redmine_ref || "\u2014"}</p>
                                  {row.notes && <p className="text-sm">{row.notes}</p>}
                                  {editable && detailIsCurrent && (
                                    <div className="flex gap-2">
                                      <Button
                                        className={buttonClass}
                                        onClick={() => {
                                          setEditingSubactivity(row);
                                          setSubForm({
                                            office: row.office,
                                            title: row.title,
                                            redmine_ref: row.redmine_ref,
                                            reserved_days: row.reserved_days,
                                            start_date: row.start_date ?? "",
                                            end_date: row.end_date ?? "",
                                            quarter_estimate_days: row.quarter_estimate_days ?? "",
                                            forecast_remaining_days:
                                              row.forecast_remaining_days ?? "",
                                            notes: row.notes,
                                          });
                                        }}
                                      >
                                        Modifica attività
                                      </Button>
                                      <Button
                                        className={dangerButtonClass}
                                        onClick={(event) => {
                                          deleteOpener.current = event.currentTarget;
                                          setFormError("");
                                          setDeleteConfirmation({
                                            title: "Elimina attivit\u00e0",
                                            description: `Confermi l'eliminazione di ${row.title}?`,
                                            confirm: () =>
                                              removeSub.mutate(row, {
                                                onSuccess: () => setDeleteConfirmation(null),
                                              }),
                                          });
                                        }}
                                      >
                                        ELIMINA
                                      </Button>
                                    </div>
                                  )}
                                  {editingSubactivity?.id === row.id && (
                                    <div className="grid gap-2 rounded border border-primary/50 bg-muted/30 p-3 sm:grid-cols-3">
                                      <div className="flex items-center justify-between sm:col-span-3">
                                        <strong>Modifica attività</strong>
                                        <Button
                                          className={buttonClass}
                                          onClick={() => {
                                            setEditingSubactivity(null);
                                            setSubForm({
                                              office: "",
                                              title: "",
                                              redmine_ref: "",
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
                                        </Button>
                                      </div>
                                      <Input
                                        className={fieldClass}
                                        aria-label="Titolo attività in modifica"
                                        value={subForm.title}
                                        onChange={(e) =>
                                          setSubForm({ ...subForm, title: e.target.value })
                                        }
                                      />
                                      <Input
                                        className={fieldClass}
                                        aria-label="Redmine in modifica"
                                        placeholder="Redmine"
                                        value={subForm.redmine_ref}
                                        onChange={(e) =>
                                          setSubForm({ ...subForm, redmine_ref: e.target.value })
                                        }
                                      />
                                      <Select
                                        className={fieldClass}
                                        aria-label="Dominio attività in modifica"
                                        value={subForm.office}
                                        onChange={(e) =>
                                          setSubForm({ ...subForm, office: e.target.value })
                                        }
                                      >
                                        {["EA", "TA", "SA", "CROSS"].map((office) => (
                                          <option key={office}>{office}</option>
                                        ))}
                                      </Select>
                                      <Input
                                        className={fieldClass}
                                        aria-label="Giornate riservate in modifica"
                                        type="number"
                                        min="0.01"
                                        step="0.01"
                                        value={subForm.reserved_days}
                                        onChange={(e) =>
                                          setSubForm({ ...subForm, reserved_days: e.target.value })
                                        }
                                      />
                                      <Input
                                        className={fieldClass}
                                        aria-label="Data inizio attività in modifica"
                                        type="date"
                                        value={subForm.start_date}
                                        onChange={(e) =>
                                          setSubForm({ ...subForm, start_date: e.target.value })
                                        }
                                      />
                                      <Input
                                        className={fieldClass}
                                        aria-label="Data fine attività in modifica"
                                        type="date"
                                        value={subForm.end_date}
                                        onChange={(e) =>
                                          setSubForm({ ...subForm, end_date: e.target.value })
                                        }
                                      />
                                      <Button
                                        className={buttonClass}
                                        onClick={() => addSub.mutate()}
                                      >
                                        Salva modifiche
                                      </Button>
                                    </div>
                                  )}
                                </Tabs.Content>
                                <Tabs.Content value="Consuntivi" className="space-y-3 pt-4">
                                  {canConsuntiva &&
                                    detailIsCurrent &&
                                    timesheetActivity !== row.id && (
                                      <Button
                                        className={buttonClass}
                                        onClick={() => {
                                          setTimesheetActivity(row.id);
                                          setEditingTimesheet(null);
                                          setTimesheetForm({
                                            data: "",
                                            giornate: "",
                                            descrizione: "",
                                          });
                                          setFormError("");
                                        }}
                                      >
                                        Nuovo consuntivo
                                      </Button>
                                    )}
                                  {timesheetActivity === row.id && (
                                    <div className="grid gap-2 rounded border border-dashed p-3 sm:grid-cols-4">
                                      <Input
                                        className={fieldClass}
                                        aria-label="Data consuntivo"
                                        type="date"
                                        value={timesheetForm.data}
                                        onChange={(e) =>
                                          setTimesheetForm({
                                            ...timesheetForm,
                                            data: e.target.value,
                                          })
                                        }
                                      />
                                      <Input
                                        className={fieldClass}
                                        aria-label="Giornate consuntivo"
                                        type="number"
                                        min="0.01"
                                        step="0.01"
                                        placeholder="Giornate"
                                        value={timesheetForm.giornate}
                                        onChange={(e) =>
                                          setTimesheetForm({
                                            ...timesheetForm,
                                            giornate: e.target.value,
                                          })
                                        }
                                      />
                                      <Input
                                        className={fieldClass}
                                        aria-label="Descrizione consuntivo"
                                        placeholder="Descrizione"
                                        value={timesheetForm.descrizione}
                                        onChange={(e) =>
                                          setTimesheetForm({
                                            ...timesheetForm,
                                            descrizione: e.target.value,
                                          })
                                        }
                                      />
                                      <Button
                                        className={buttonClass}
                                        disabled={saveTimesheet.isPending}
                                        onClick={() => saveTimesheet.mutate()}
                                      >
                                        {editingTimesheet ? "Salva rettifica" : "Registra"}
                                      </Button>
                                      <Button
                                        className={buttonClass}
                                        onClick={() => {
                                          setTimesheetActivity(null);
                                          setEditingTimesheet(null);
                                          setFormError("");
                                        }}
                                      >
                                        Annulla
                                      </Button>
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
                                            {canEditConsuntivi && <th>Azioni</th>}
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
                                              {canEditConsuntivi && (
                                                <td className="flex gap-2 py-1">
                                                  <Button
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
                                                  </Button>
                                                  <Button
                                                    className={buttonClass}
                                                    onClick={(event) => {
                                                      deleteOpener.current = event.currentTarget;
                                                      setFormError("");
                                                      setDeleteConfirmation({
                                                        title: "Elimina consuntivo",
                                                        description: `Confermi l'eliminazione del consuntivo del ${entry.data}?`,
                                                        confirm: () =>
                                                          removeTimesheet.mutate(
                                                            {
                                                              activityId: row.id,
                                                              entryId: entry.id,
                                                            },
                                                            {
                                                              onSuccess: () =>
                                                                setDeleteConfirmation(null),
                                                            },
                                                          ),
                                                      });
                                                    }}
                                                  >
                                                    Elimina
                                                  </Button>
                                                </td>
                                              )}
                                            </tr>
                                          ))}
                                        </tbody>
                                      </table>
                                    </div>
                                  )}
                                  {row.consuntivi.length === 0 && (
                                    <p className="text-sm text-muted-foreground">
                                      Nessun consuntivo registrato.
                                    </p>
                                  )}
                                </Tabs.Content>
                              </Tabs.Root>
                            </>
                          )}
                        </div>
                      ))
                  )}
                  {editable &&
                    detailIsCurrent &&
                    !editingSubactivity &&
                    !selectedActivity &&
                    !creatingActivity && (
                      <Button
                        variant="secondary"
                        onClick={() => {
                          setCreatingActivity(true);
                          setFormError("");
                        }}
                      >
                        Nuova attività
                      </Button>
                    )}
                  {editable &&
                    detailIsCurrent &&
                    !editingSubactivity &&
                    !selectedActivity &&
                    creatingActivity && (
                      <div className="grid gap-2 rounded border border-dashed p-3 sm:grid-cols-3">
                        <Input
                          className={fieldClass}
                          aria-label="Titolo attività"
                          placeholder="Titolo attività"
                          value={subForm.title}
                          onChange={(e) => setSubForm({ ...subForm, title: e.target.value })}
                        />
                        <Input
                          className={fieldClass}
                          aria-label="Redmine"
                          placeholder="Redmine"
                          value={subForm.redmine_ref}
                          onChange={(e) => setSubForm({ ...subForm, redmine_ref: e.target.value })}
                        />
                        <Select
                          className={fieldClass}
                          aria-label="Gruppo architetturale"
                          value={subForm.office}
                          onChange={(e) => setSubForm({ ...subForm, office: e.target.value })}
                        >
                          <option value="">Gruppo</option>
                          {["EA", "TA", "SA", "CROSS"].map((office) => (
                            <option key={office}>{office}</option>
                          ))}
                        </Select>
                        <Input
                          className={fieldClass}
                          aria-label="Giornate da riservare"
                          type="number"
                          min="0.01"
                          step="0.01"
                          placeholder="Giornate da riservare"
                          value={subForm.reserved_days}
                          onChange={(e) =>
                            setSubForm({ ...subForm, reserved_days: e.target.value })
                          }
                        />
                        <Input
                          className={fieldClass}
                          aria-label="Data inizio attività"
                          type="date"
                          value={subForm.start_date}
                          onChange={(e) => setSubForm({ ...subForm, start_date: e.target.value })}
                        />
                        <Input
                          className={fieldClass}
                          aria-label="Data fine attività"
                          type="date"
                          value={subForm.end_date}
                          onChange={(e) => setSubForm({ ...subForm, end_date: e.target.value })}
                        />
                        <Button
                          className={buttonClass}
                          disabled={addSub.isPending}
                          onClick={() => addSub.mutate()}
                        >
                          Aggiungi attività
                        </Button>
                        <Button variant="secondary" onClick={() => setCreatingActivity(false)}>
                          Annulla
                        </Button>
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
