import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface TimesheetAuthor {
  id: number;
  username: string;
  full_name: string;
  roles: string[];
}

/**
 * Utenti indicabili come autori di un consuntivo. L'endpoint è riservato ad Admin:
 * si interroga solo quando la sessione ha `timesheets.assign_author`.
 */
/** Invalidata dal pannello utenti dell'area Admin dopo ogni creazione o modifica. */
export const TIMESHEET_AUTHORS_KEY = ["timesheets", "authors"] as const;

export function useTimesheetAuthors(enabled: boolean) {
  return useQuery({
    queryKey: TIMESHEET_AUTHORS_KEY,
    queryFn: () => api.get<{ results: TimesheetAuthor[] }>("/timesheets/authors"),
    enabled,
    // Niente staleTime: un utente appena creato deve comparire subito nel select,
    // senza aspettare la scadenza di una cache. La lista e corta.
    refetchOnMount: "always",
  });
}

export function authorLabel(author: TimesheetAuthor): string {
  return author.full_name && author.full_name !== author.username
    ? `${author.full_name} (${author.username})`
    : author.username;
}
