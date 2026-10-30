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
export function useTimesheetAuthors(enabled: boolean) {
  return useQuery({
    queryKey: ["timesheets", "authors"],
    queryFn: () => api.get<{ results: TimesheetAuthor[] }>("/timesheets/authors"),
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}

export function authorLabel(author: TimesheetAuthor): string {
  return author.full_name && author.full_name !== author.username
    ? `${author.full_name} (${author.username})`
    : author.username;
}
