import { useDialogFocusReturn } from "@/lib/useDialogFocusReturn";
import { Button, Input } from "@/components/Controls";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AlertTriangle, CheckCircle, Lock, RefreshCw, X } from "lucide-react";

import { api, ApiError } from "@/lib/api";

interface ResetPreviewResponse {
  preview: Record<string, number>;
  total_records: number;
  confirmation_keyword: string;
  token: string;
}

interface DeleteDatabaseDialogProps {
  open: boolean;
  onClose: () => void;
}

export function DeleteDatabaseDialog({ open, onClose }: DeleteDatabaseDialogProps) {
  const queryClient = useQueryClient();
  const dialogFocus = useDialogFocusReturn('[data-testid="open-delete-db-dialog-btn"]');
  const [confirmationInput, setConfirmationInput] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const previewQuery = useQuery({
    queryKey: ["admin", "reset-data-preview"],
    queryFn: () => api.get<ResetPreviewResponse>("/admin/reset-data"),
    enabled: open,
    staleTime: 0,
  });

  const resetMutation = useMutation({
    mutationFn: async () => {
      if (!previewQuery.data?.token) {
        throw new Error("Token di sicurezza non disponibile. Ricarica e riprova.");
      }
      return api.post<{ status: string; detail: string; deleted: Record<string, number> }>(
        "/admin/reset-data",
        {
          confirmation: confirmationInput.trim(),
          token: previewQuery.data.token,
        },
      );
    },
    onSuccess: (data) => {
      setSuccessMessage(data.detail || "Tutti i dati operativi sono stati eliminati con successo.");
      setErrorMessage(null);
      void queryClient.clear();
      void queryClient.invalidateQueries();
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError) {
        const body = err.problem;
        setErrorMessage(body?.detail || body?.title || err.message);
        return;
      }
      setErrorMessage(err instanceof Error ? err.message : "Errore durante il reset dei dati.");
    },
  });

  const handleClose = () => {
    setConfirmationInput("");
    setErrorMessage(null);
    setSuccessMessage(null);
    onClose();
  };

  const isConfirmed = confirmationInput.trim() === "ELIMINA";

  return (
    <Dialog.Root open={open} onOpenChange={(isOpen) => !isOpen && handleClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-slate-950/70 backdrop-blur-sm transition-opacity" />
        <Dialog.Content
          {...dialogFocus}
          aria-describedby="delete-db-summary"
          className="fixed left-1/2 top-1/2 z-50 max-h-[90dvh] w-[calc(100vw-2rem)] max-w-xl -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border-2 border-danger/60 bg-card p-6 shadow-2xl focus:outline-none"
        >
          <Dialog.Description id="delete-db-summary" className="sr-only">
            Eliminazione dei dati operativi. Richiede verifica e conferma esplicita.
          </Dialog.Description>
          <div className="flex items-center justify-between border-b border-border pb-3">
            <div className="flex items-center gap-2 text-danger">
              <AlertTriangle className="h-6 w-6" />
              <Dialog.Title className="text-lg font-bold">
                Sei sicuro di voler eliminare il DB?
              </Dialog.Title>
            </div>
            <Dialog.Close asChild>
              <Button
                type="button"
                className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                aria-label="Chiudi"
              >
                <X className="h-5 w-5" />
              </Button>
            </Dialog.Close>
          </div>

          <div id="delete-db-dialog-description" className="mt-4 space-y-4 text-sm">
            {successMessage ? (
              <div className="space-y-4 py-4 text-center">
                <div className="flex items-center justify-center gap-2 text-base font-semibold text-ok">
                  <CheckCircle className="h-6 w-6" />
                  <span>{successMessage}</span>
                </div>
                <p className="text-xs text-muted-foreground">
                  Gli account utente e i privilegi sono stati conservati. È ora possibile importare
                  un nuovo dataset pulito.
                </p>
                <Button
                  type="button"
                  onClick={handleClose}
                  className="rounded bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground"
                >
                  Chiudi e torna all'amministrazione
                </Button>
              </div>
            ) : (
              <>
                <div className="rounded-md border border-danger/30 bg-danger/10 p-3 text-xs leading-relaxed text-foreground">
                  <p className="font-semibold text-danger">ATTENZIONE: Operazione irreversibile!</p>
                  <p className="mt-1">
                    Questa procedura cancellerà tutti i <strong>progetti</strong>,{" "}
                    <strong>consuntivi</strong>, <strong>allocazioni wallet</strong>,{" "}
                    <strong>organico allargato (canoni)</strong>, <strong>importazioni</strong> e{" "}
                    <strong>anomalie</strong>.
                  </p>
                  <p className="mt-1 text-muted-foreground">
                    Gli utenti, le password, i gruppi, i privilegi configurati e le impostazioni
                    generali <strong>NON</strong> verranno eliminati.
                  </p>
                </div>

                {previewQuery.isLoading ? (
                  <div className="flex items-center justify-center gap-2 py-6 text-xs text-muted-foreground">
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    <span>Calcolo record da eliminare...</span>
                  </div>
                ) : previewQuery.isError ? (
                  <div className="rounded border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive">
                    Impossibile ottenere l'anteprima dei record. Riprova più tardi.
                  </div>
                ) : (
                  previewQuery.data && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-xs font-medium">
                        <span>Riepilogo record operativi:</span>
                        <span className="font-mono font-bold text-foreground">
                          Totale: {previewQuery.data.total_records} record
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 rounded bg-muted/40 p-2.5 text-[11px] sm:grid-cols-3">
                        {Object.entries(previewQuery.data.preview).map(([name, count]) => (
                          <div
                            key={name}
                            className="flex justify-between border-b border-border/50 py-0.5"
                          >
                            <span className="capitalize text-muted-foreground">{name}:</span>
                            <span className="font-mono font-semibold">{count}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )
                )}

                {errorMessage && (
                  <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive">
                    {errorMessage}
                  </div>
                )}

                <div className="space-y-2 rounded-md border border-border bg-card p-3">
                  <label
                    htmlFor="confirm-elimina-input"
                    className="block text-xs font-semibold text-foreground"
                  >
                    Controverifica obbligatoria:
                  </label>
                  <p className="text-[11px] text-muted-foreground">
                    Per confermare l'eliminazione, digita esattamente <strong>ELIMINA</strong> nel
                    campo seguente:
                  </p>
                  <Input
                    id="confirm-elimina-input"
                    data-testid="delete-db-confirmation-input"
                    type="text"
                    autoComplete="off"
                    value={confirmationInput}
                    onChange={(e) => setConfirmationInput(e.target.value)}
                    placeholder="ELIMINA"
                    className="w-full rounded border border-danger/60 bg-background px-3 py-1.5 font-mono text-sm uppercase tracking-wider text-foreground focus:border-danger focus:outline-none"
                  />
                </div>

                <div className="flex items-center justify-between border-t border-border pt-4">
                  <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                    <Lock className="h-3 w-3" /> Richiede capability data.reset
                  </span>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      onClick={handleClose}
                      className="rounded border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted"
                    >
                      Annulla
                    </Button>
                    <Button
                      type="button"
                      disabled={!isConfirmed || resetMutation.isPending || previewQuery.isLoading}
                      onClick={() => resetMutation.mutate()}
                      data-testid="confirm-delete-db-btn"
                      className="inline-flex items-center justify-center rounded bg-danger-action px-4 py-1.5 text-xs font-bold uppercase tracking-wider text-white shadow-sm transition hover:bg-danger-action/90 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {resetMutation.isPending ? "Eliminazione..." : "Conferma eliminazione DB"}
                    </Button>
                  </div>
                </div>
              </>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
