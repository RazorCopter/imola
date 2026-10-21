import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { api } from "@/lib/api";

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
interface SearchResult {
  tipo: string;
  id: string;
  codice: string;
  titolo: string;
  url: string;
}
interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CommandPalette({ open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const query = useQuery({
    queryKey: ["command-search", search],
    queryFn: () => api.get<{ results: SearchResult[] }>(`/search?q=${encodeURIComponent(search)}`),
    enabled: open && search.trim().length >= 2,
  });
  const select = (to: string) => {
    navigate(to);
    onOpenChange(false);
    setSearch("");
  };
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 animate-fade-in bg-black/40" />
        <Dialog.Content className="fixed left-1/2 top-24 z-50 w-[min(34rem,calc(100vw-2rem))] -translate-x-1/2 animate-slide-up overflow-hidden rounded-lg border border-border bg-card shadow-raised">
          <Dialog.Title className="sr-only">{t("app.commandPalette")}</Dialog.Title>
          <Command label={t("app.commandPalette")} shouldFilter={false}>
            <Command.Input
              autoFocus
              value={search}
              onValueChange={setSearch}
              placeholder={t("app.commandPalette")}
              className="h-12 w-full border-b border-border bg-transparent px-4 text-sm outline-none"
            />
            <Command.List className="max-h-80 overflow-y-auto p-2">
              <Command.Empty className="p-4 text-center text-sm text-muted-foreground">
                {search.length < 2 ? "Digita almeno due caratteri" : t("app.empty")}
              </Command.Empty>
              <Command.Group heading="Navigazione" className="text-xs text-muted-foreground">
                {ACTIONS.map((action) => (
                  <Command.Item
                    key={action.to}
                    value={action.to}
                    onSelect={() => select(action.to)}
                    className="cursor-pointer rounded-md px-3 py-2 text-sm text-foreground aria-selected:bg-muted"
                  >
                    {t(action.label)}
                  </Command.Item>
                ))}
              </Command.Group>
              {(query.data?.results.length ?? 0) > 0 && (
                <Command.Group heading="Risultati" className="mt-2 text-xs text-muted-foreground">
                  {query.data?.results.map((result) => (
                    <Command.Item
                      key={`${result.tipo}-${result.id}`}
                      value={`${result.tipo}-${result.id}`}
                      onSelect={() => select(result.url)}
                      className="cursor-pointer rounded-md px-3 py-2 text-sm text-foreground aria-selected:bg-muted"
                    >
                      <span className="mr-2 rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase">
                        {result.tipo.replace("_", " ")}
                      </span>
                      <span className="font-mono">{result.codice}</span>
                      <span className="ml-2 truncate text-muted-foreground">{result.titolo}</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
            </Command.List>
          </Command>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
