import * as Dialog from "@radix-ui/react-dialog";
import { Command } from "cmdk";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

/**
 * Ricerca globale (Ctrl/Cmd+K). In Fase 1 copre la navigazione; progetti, attività e
 * anomalie si agganciano qui quando le relative API di ricerca sono attive.
 */
const ACTIONS = [
  { to: "/", label: "nav.dashboard" },
  { to: "/progetti", label: "nav.projects" },
  { to: "/wallet", label: "nav.wallet" },
  { to: "/canone", label: "nav.canone" },
  { to: "/riconciliazione", label: "nav.reconciliation" },
  { to: "/anomalie", label: "nav.anomalies" },
  { to: "/revisione", label: "nav.review" },
  { to: "/amministrazione", label: "nav.admin" },
] as const;

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CommandPalette({ open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 animate-fade-in bg-black/40" />
        <Dialog.Content className="fixed left-1/2 top-24 z-50 w-[min(34rem,calc(100vw-2rem))] -translate-x-1/2 animate-slide-up overflow-hidden rounded-lg border border-border bg-card shadow-raised">
          <Dialog.Title className="sr-only">{t("app.commandPalette")}</Dialog.Title>
          <Command label={t("app.commandPalette")}>
            <Command.Input
              autoFocus
              placeholder={t("app.commandPalette")}
              className="h-12 w-full border-b border-border bg-transparent px-4 text-sm outline-none"
            />
            <Command.List className="max-h-72 overflow-auto p-2">
              <Command.Empty className="px-3 py-6 text-center text-sm text-muted-foreground">
                {t("app.empty")}
              </Command.Empty>
              <Command.Group
                heading={t("nav.dashboard")}
                className="px-1 text-xs text-muted-foreground"
              >
                {ACTIONS.map((action) => (
                  <Command.Item
                    key={action.to}
                    value={t(action.label)}
                    onSelect={() => {
                      navigate(action.to);
                      onOpenChange(false);
                    }}
                    className="cursor-pointer rounded-md px-3 py-2 text-sm text-foreground aria-selected:bg-accent-subtle aria-selected:text-accent"
                  >
                    {t(action.label)}
                  </Command.Item>
                ))}
              </Command.Group>
            </Command.List>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
