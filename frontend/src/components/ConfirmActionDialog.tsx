import * as Dialog from "@radix-ui/react-dialog";
import { useRef } from "react";
import { Button } from "./Controls";
export function ConfirmActionDialog({
  open,
  title,
  description,
  pending,
  error,
  onConfirm,
  onOpenChange,
  returnFocusTo,
}: {
  open: boolean;
  title: string;
  description: string;
  pending: boolean;
  error?: string;
  onConfirm: () => void;
  onOpenChange: (open: boolean) => void;
  returnFocusTo?: HTMLElement | null;
}) {
  const cancel = useRef<HTMLButtonElement>(null);
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(value) => {
        if (!pending) onOpenChange(value);
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 max-h-[90dvh] w-[min(30rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl border border-border bg-card p-6 shadow-raised"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            cancel.current?.focus();
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            if (returnFocusTo?.isConnected) returnFocusTo.focus();
            else document.querySelector<HTMLElement>("main button:not([disabled])")?.focus();
          }}
        >
          <Dialog.Title className="text-lg font-semibold">{title}</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-muted-foreground">
            {description}
          </Dialog.Description>
          {error && (
            <p role="alert" className="mt-3 rounded bg-danger-subtle p-3 text-sm text-danger">
              {error}
            </p>
          )}
          <div className="mt-6 flex justify-end gap-3">
            <Dialog.Close asChild>
              <Button ref={cancel} variant="secondary" disabled={pending}>
                Annulla
              </Button>
            </Dialog.Close>
            <Button variant="danger" disabled={pending} onClick={onConfirm}>
              {pending ? "Eliminazione..." : "ELIMINA"}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
