import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { AlertCircle, Lock } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { useSession } from "@/features/auth/session";
import { canEditProjects } from "@/lib/permissions";

export interface ProjectFormData {
  id: string;
  code: string;
  title: string;
  contract_type: string;
  aro_code: string;
  rda_code: string;
  deliverable: string;
  client_owner: string | null;
  supplier_owner: string | null;
  budget_days: string;
  start_date: string | null;
  planned_end_date: string | null;
  actual_closure_date: string | null;
  offer_status: string;
  timesheet_status: string;
  billing_status: string;
  notes: string;
  reliability: string;
  verification_points: unknown[];
  version: number;
  permissions: {
    edit: boolean;
    annotate: boolean;
    editable_fields: string[];
  };
  readonly?: Record<string, string>;
}

export interface ProjectOptions {
  contract_types: { value: string; label: string }[];
  offer_statuses: { value: string; label: string }[];
  timesheet_statuses: { value: string; label: string }[];
  billing_statuses: { value: string; label: string }[];
  reliabilities: { value: string; label: string }[];
  organizations: { id: string; code: string; name: string; kind: string }[];
  people: { id: string; name: string; organization_id: string; organization_kind: string }[];
}

interface FormValues {
  title: string;
  contract_type: string;
  aro_code: string;
  rda_code: string;
  deliverable: string;
  client_owner: string;
  supplier_owner: string;
  budget_days: string;
  start_date: string;
  planned_end_date: string;
  actual_closure_date: string;
  offer_status: string;
  timesheet_status: string;
  billing_status: string;
  notes: string;
  reliability: string;
}

interface EditProjectDialogProps {
  projectId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trigger?: React.ReactNode;
}

export function EditProjectDialog({
  projectId,
  open,
  onOpenChange,
  trigger,
}: EditProjectDialogProps) {
  const queryClient = useQueryClient();
  const { session } = useSession();
  const [genericError, setGenericError] = useState<string | null>(null);

  const detailQuery = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.get<ProjectFormData>(`/projects/${projectId}`),
    enabled: open && Boolean(projectId),
  });

  const optionsQuery = useQuery({
    queryKey: ["project-options"],
    queryFn: () => api.get<ProjectOptions>("/projects/options"),
    enabled: open,
    staleTime: 5 * 60 * 1000,
  });

  const {
    register,
    handleSubmit,
    reset,
    setError,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>();

  const project = detailQuery.data;
  const isFullEdit = Boolean(project?.permissions?.edit ?? canEditProjects(session));

  useEffect(() => {
    if (project) {
      reset({
        title: project.title ?? "",
        contract_type: project.contract_type ?? "AQL",
        aro_code: project.aro_code ?? "",
        rda_code: project.rda_code ?? "",
        deliverable: project.deliverable ?? "",
        client_owner: project.client_owner ?? "",
        supplier_owner: project.supplier_owner ?? "",
        budget_days: project.budget_days ?? "0.0000",
        start_date: project.start_date ?? "",
        planned_end_date: project.planned_end_date ?? "",
        actual_closure_date: project.actual_closure_date ?? "",
        offer_status: project.offer_status ?? "INVIATA",
        timesheet_status: project.timesheet_status ?? "NON_AVVIATO",
        billing_status: project.billing_status ?? "DA_FATTURARE",
        notes: project.notes ?? "",
        reliability: project.reliability ?? "CERTO",
      });
      setGenericError(null);
    }
  }, [project, reset]);

  const watchedTimesheetStatus = watch("timesheet_status");

  const clientPeople = useMemo(
    () => optionsQuery.data?.people.filter((p) => p.organization_kind === "CLIENT") ?? [],
    [optionsQuery.data],
  );
  const supplierPeople = useMemo(
    () => optionsQuery.data?.people.filter((p) => p.organization_kind === "SUPPLIER") ?? [],
    [optionsQuery.data],
  );

  const mutation = useMutation({
    mutationFn: async (values: FormValues) => {
      if (!project) return;
      const payload: Record<string, unknown> = {
        expected_version: project.version,
      };

      if (isFullEdit) {
        payload.title = values.title;
        payload.contract_type = values.contract_type;
        payload.aro_code = values.aro_code;
        payload.rda_code = values.rda_code;
        payload.deliverable = values.deliverable;
        payload.client_owner = values.client_owner || null;
        payload.supplier_owner = values.supplier_owner || null;
        payload.budget_days = values.budget_days;
        payload.start_date = values.start_date || null;
        payload.planned_end_date = values.planned_end_date || null;
        payload.actual_closure_date = values.actual_closure_date || null;
        payload.offer_status = values.offer_status;
        payload.timesheet_status = values.timesheet_status;
        payload.billing_status = values.billing_status;
        payload.notes = values.notes;
        payload.reliability = values.reliability;
      } else {
        payload.notes = values.notes;
        payload.planned_end_date = values.planned_end_date || null;
      }

      return api.patch<ProjectFormData>(`/projects/${projectId}`, payload);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      await queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      await queryClient.invalidateQueries({ queryKey: ["audit", "project", projectId] });
      onOpenChange(false);
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        if (error.status === 409 || error.code === "risorsa-modificata") {
          setGenericError(
            error.problem.detail ||
              "La risorsa è stata modificata da un altro utente. Ricarica la scheda per riprovare.",
          );
          void detailQuery.refetch();
          return;
        }
        if (error.status === 428) {
          setGenericError("Precondizione richiesta: versione non valida. Riapri il form.");
          return;
        }
        if (error.fieldErrors && Object.keys(error.fieldErrors).length > 0) {
          Object.entries(error.fieldErrors).forEach(([field, message]) => {
            setError(field as keyof FormValues, { message });
          });
          return;
        }
        setGenericError(
          error.problem.detail || error.problem.title || "Errore durante il salvataggio.",
        );
      } else {
        setGenericError("Si è verificato un errore di rete inatteso.");
      }
    },
  });

  const onSubmit = (values: FormValues) => {
    setGenericError(null);
    mutation.mutate(values);
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      {trigger && <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>}
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-full max-w-3xl -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border border-border bg-card p-6 shadow-xl">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <div>
              <Dialog.Title className="text-lg font-semibold text-foreground">
                Modifica Progetto
              </Dialog.Title>
              <Dialog.Description className="text-xs text-muted-foreground">
                {isFullEdit
                  ? "Modifica anagrafica, contratti, stato e date del progetto."
                  : "Modifica campi annotazione consentiti per il referente."}
              </Dialog.Description>
            </div>
            {project && (
              <span className="rounded bg-muted px-2 py-1 font-mono text-xs text-muted-foreground">
                v{project.version}
              </span>
            )}
          </div>

          {detailQuery.isLoading ? (
            <div className="py-12 text-center text-sm text-muted-foreground">
              Caricamento anagrafica...
            </div>
          ) : detailQuery.isError ? (
            <div className="text-destructive py-8 text-center text-sm">
              Impossibile caricare i dati del progetto. Riprova più tardi.
            </div>
          ) : (
            <form
              onSubmit={(e) => {
                void handleSubmit(onSubmit)(e);
              }}
              className="mt-4 space-y-4"
            >
              {genericError && (
                <div className="bg-destructive/15 text-destructive flex items-center gap-2 rounded-md p-3 text-sm">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  <span>{genericError}</span>
                </div>
              )}

              {/* Codice Progetto (Sempre Readonly) */}
              <div className="rounded-md border border-amber-500/20 bg-amber-500/5 p-3">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold uppercase text-muted-foreground">
                    Codice Progetto (Read-only)
                  </label>
                  <span className="flex items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
                    <Lock className="h-3 w-3" /> Bloccato
                  </span>
                </div>
                <div className="mt-1 font-mono text-sm font-medium text-foreground">
                  {project?.code}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {project?.readonly?.code ||
                    "Il codice è bloccato perché può essere referenziato da import e ledger."}
                </p>
              </div>

              {/* Dati Generali */}
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className="md:col-span-2">
                  <label className="text-xs font-medium text-foreground">Titolo</label>
                  <input
                    {...register("title")}
                    disabled={!isFullEdit}
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm disabled:opacity-60"
                  />
                  {errors.title && (
                    <p className="text-destructive mt-0.5 text-xs">{errors.title.message}</p>
                  )}
                </div>

                <div>
                  <label className="text-xs font-medium text-foreground">Tipo Contratto</label>
                  <select
                    {...register("contract_type")}
                    disabled={!isFullEdit}
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm disabled:opacity-60"
                  >
                    {optionsQuery.data?.contract_types.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                  {errors.contract_type && (
                    <p className="text-destructive mt-0.5 text-xs">
                      {errors.contract_type.message}
                    </p>
                  )}
                </div>

                <div>
                  <label className="text-xs font-medium text-foreground">Budget (giornate)</label>
                  <input
                    {...register("budget_days")}
                    disabled={!isFullEdit}
                    step="0.0001"
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 font-mono text-sm disabled:opacity-60"
                  />
                  {errors.budget_days && (
                    <p className="text-destructive mt-0.5 text-xs">{errors.budget_days.message}</p>
                  )}
                </div>

                <div>
                  <label className="text-xs font-medium text-foreground">Codice ARO</label>
                  <input
                    {...register("aro_code")}
                    disabled={!isFullEdit}
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm disabled:opacity-60"
                  />
                </div>

                <div>
                  <label className="text-xs font-medium text-foreground">Codice RDA</label>
                  <input
                    {...register("rda_code")}
                    disabled={!isFullEdit}
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm disabled:opacity-60"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="text-xs font-medium text-foreground">Deliverable</label>
                  <input
                    {...register("deliverable")}
                    disabled={!isFullEdit}
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm disabled:opacity-60"
                  />
                </div>
              </div>

              {/* Referenti */}
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div>
                  <label className="text-xs font-medium text-foreground">
                    Referente Cliente (BMED)
                  </label>
                  <select
                    {...register("client_owner")}
                    disabled={!isFullEdit}
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm disabled:opacity-60"
                  >
                    <option value="">-- Nessun referente --</option>
                    {clientPeople.map((person) => (
                      <option key={person.id} value={person.id}>
                        {person.name}
                      </option>
                    ))}
                  </select>
                  {errors.client_owner && (
                    <p className="text-destructive mt-0.5 text-xs">{errors.client_owner.message}</p>
                  )}
                </div>

                <div>
                  <label className="text-xs font-medium text-foreground">
                    Referente Fornitore (Imola)
                  </label>
                  <select
                    {...register("supplier_owner")}
                    disabled={!isFullEdit}
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm disabled:opacity-60"
                  >
                    <option value="">-- Nessun referente --</option>
                    {supplierPeople.map((person) => (
                      <option key={person.id} value={person.id}>
                        {person.name}
                      </option>
                    ))}
                  </select>
                  {errors.supplier_owner && (
                    <p className="text-destructive mt-0.5 text-xs">
                      {errors.supplier_owner.message}
                    </p>
                  )}
                </div>
              </div>

              {/* Stati */}
              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <div>
                  <label className="text-xs font-medium text-foreground">Stato Offerta</label>
                  <select
                    {...register("offer_status")}
                    disabled={!isFullEdit}
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm disabled:opacity-60"
                  >
                    {optionsQuery.data?.offer_statuses.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                  {errors.offer_status && (
                    <p className="text-destructive mt-0.5 text-xs">{errors.offer_status.message}</p>
                  )}
                </div>

                <div>
                  <label className="text-xs font-medium text-foreground">
                    Stato Consuntivazione
                  </label>
                  <select
                    {...register("timesheet_status")}
                    disabled={!isFullEdit}
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm disabled:opacity-60"
                  >
                    {optionsQuery.data?.timesheet_statuses.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                  {errors.timesheet_status && (
                    <p className="text-destructive mt-0.5 text-xs">
                      {errors.timesheet_status.message}
                    </p>
                  )}
                </div>

                <div>
                  <label className="text-xs font-medium text-foreground">Stato Fatturazione</label>
                  <select
                    {...register("billing_status")}
                    disabled={!isFullEdit}
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm disabled:opacity-60"
                  >
                    {optionsQuery.data?.billing_statuses.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                  {errors.billing_status && (
                    <p className="text-destructive mt-0.5 text-xs">
                      {errors.billing_status.message}
                    </p>
                  )}
                </div>
              </div>

              {/* Date */}
              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <div>
                  <label className="text-xs font-medium text-foreground">Data Inizio</label>
                  <input
                    type="date"
                    {...register("start_date")}
                    disabled={!isFullEdit}
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm disabled:opacity-60"
                  />
                  {errors.start_date && (
                    <p className="text-destructive mt-0.5 text-xs">{errors.start_date.message}</p>
                  )}
                </div>

                <div>
                  <label className="text-xs font-medium text-foreground">Fine Prevista</label>
                  <input
                    type="date"
                    {...register("planned_end_date")}
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm"
                  />
                  {errors.planned_end_date && (
                    <p className="text-destructive mt-0.5 text-xs">
                      {errors.planned_end_date.message}
                    </p>
                  )}
                </div>

                <div>
                  <label className="text-xs font-medium text-foreground">
                    Data Chiusura Effettiva
                    {watchedTimesheetStatus === "CHIUSO" && (
                      <span className="text-destructive ml-1 font-bold">*</span>
                    )}
                  </label>
                  <input
                    type="date"
                    {...register("actual_closure_date")}
                    disabled={!isFullEdit}
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm disabled:opacity-60"
                  />
                  {errors.actual_closure_date && (
                    <p className="text-destructive mt-0.5 text-xs">
                      {errors.actual_closure_date.message}
                    </p>
                  )}
                  {watchedTimesheetStatus === "CHIUSO" && (
                    <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                      Obbligatoria per progetti CHIUSO (D-03/D-14).
                    </p>
                  )}
                </div>
              </div>

              {/* Note */}
              <div>
                <label className="text-xs font-medium text-foreground">Note & Annotazioni</label>
                <textarea
                  {...register("notes")}
                  rows={3}
                  className="mt-1 w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm"
                  placeholder="Note sul progetto o annotazioni di verifica..."
                />
                {errors.notes && (
                  <p className="text-destructive mt-0.5 text-xs">{errors.notes.message}</p>
                )}
              </div>

              {/* Footer con pulsanti */}
              <div className="flex items-center justify-end gap-3 border-t border-border pt-4">
                <button
                  type="button"
                  onClick={() => onOpenChange(false)}
                  className="rounded-md border border-border px-4 py-2 text-sm font-medium text-muted-foreground hover:bg-muted"
                >
                  Annulla
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting || mutation.isPending}
                  className="rounded-md bg-amber-500 px-4 py-2 text-sm font-semibold text-slate-950 shadow-sm hover:bg-amber-400 disabled:opacity-50"
                >
                  {mutation.isPending ? "Salvataggio..." : "Salva Modifiche"}
                </button>
              </div>
            </form>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
