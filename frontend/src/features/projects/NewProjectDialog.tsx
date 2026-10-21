import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { api, ApiError } from "@/lib/api";

interface FormValues {
  code: string;
  title: string;
  contract_type: string;
  budget_days: string;
  start_date: string;
  planned_end_date: string;
}

export function NewProjectDialog() {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(1);
  const queryClient = useQueryClient();
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
    setError,
    reset,
  } = useForm<FormValues>({ defaultValues: { contract_type: "AQL", budget_days: "0" } });
  const mutation = useMutation({
    mutationFn: (values: FormValues) => api.post<{ id: string }>("/projects", values),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      reset();
      setStep(1);
      setOpen(false);
    },
    onError: (error) => {
      if (error instanceof ApiError)
        Object.entries(error.fieldErrors).forEach(([field, message]) =>
          setError(field as keyof FormValues, { message }),
        );
    },
  });
  const values = watch();
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-accent-foreground">
          Nuovo progetto
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(38rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-card p-5 shadow-raised">
          <Dialog.Title className="text-lg font-semibold">
            Nuovo progetto · passo {step} di 3
          </Dialog.Title>
          <form
            className="mt-4 space-y-4"
            onSubmit={(event) => {
              void handleSubmit((data) => mutation.mutate(data))(event);
            }}
          >
            {step === 1 && (
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Codice" error={errors.code?.message}>
                  <input
                    {...register("code", { required: "Campo obbligatorio" })}
                    className="input"
                  />
                </Field>
                <Field label="Tipo contratto">
                  <select {...register("contract_type")} className="input">
                    <option>AQL</option>
                    <option>CORPO</option>
                    <option>PPM</option>
                    <option>ATTIVITA</option>
                  </select>
                </Field>
                <Field label="Titolo" error={errors.title?.message}>
                  <input
                    {...register("title", { required: "Campo obbligatorio" })}
                    className="input"
                  />
                </Field>
                <Field label="Budget (gg)" error={errors.budget_days?.message}>
                  <input
                    {...register("budget_days", {
                      required: "Campo obbligatorio",
                      pattern: {
                        value: /^\d+(?:[.,]\d{1,4})?$/,
                        message: "Inserire un numero con massimo 4 decimali",
                      },
                    })}
                    className="input"
                    inputMode="decimal"
                  />
                </Field>
              </div>
            )}
            {step === 2 && (
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Data inizio">
                  <input {...register("start_date")} type="date" className="input" />
                </Field>
                <Field label="Fine prevista">
                  <input {...register("planned_end_date")} type="date" className="input" />
                </Field>
              </div>
            )}
            {step === 3 && (
              <div className="rounded-md bg-muted p-4 text-sm">
                <p>
                  <strong>{values.code}</strong> · {values.title}
                </p>
                <p>
                  {values.contract_type} · budget {values.budget_days} gg
                </p>
                <p>
                  {values.start_date || "Inizio non indicato"} →{" "}
                  {values.planned_end_date || "Fine non indicata"}
                </p>
              </div>
            )}
            {mutation.isError && (
              <p className="text-sm text-danger">
                Impossibile creare il progetto. Correggere i campi indicati.
              </p>
            )}
            <div className="flex justify-between">
              <Dialog.Close className="text-sm text-muted-foreground">Annulla</Dialog.Close>
              <div className="flex gap-2">
                {step > 1 && (
                  <button
                    type="button"
                    className="rounded-md border border-border px-3 py-2 text-sm"
                    onClick={() => setStep((value) => value - 1)}
                  >
                    Indietro
                  </button>
                )}
                {step < 3 ? (
                  <button
                    type="button"
                    className="rounded-md bg-accent px-3 py-2 text-sm text-accent-foreground"
                    onClick={(event) => {
                      void handleSubmit(() => setStep((value) => value + 1))(event);
                    }}
                  >
                    Continua
                  </button>
                ) : (
                  <button
                    disabled={mutation.isPending}
                    className="rounded-md bg-accent px-3 py-2 text-sm text-accent-foreground disabled:opacity-50"
                  >
                    Crea progetto
                  </button>
                )}
              </div>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="grid gap-1 text-sm">
      <span className="font-medium">{label}</span>
      {children}
      {error && <span className="text-xs text-danger">{error}</span>}
    </label>
  );
}
