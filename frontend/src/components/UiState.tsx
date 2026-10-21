import type { ReactNode } from "react";
import { AlertCircle, Inbox } from "lucide-react";

export function LoadingState({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2" role="status" aria-label="Caricamento">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="skeleton h-10 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="flex min-h-48 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border p-8 text-center">
      <Inbox className="size-7 text-muted-foreground" aria-hidden />
      <p className="font-medium">{title}</p>
      {detail && <p className="max-w-md text-sm text-muted-foreground">{detail}</p>}
    </div>
  );
}

export function ErrorState({
  title,
  detail,
  action,
}: {
  title: string;
  detail?: string;
  action?: ReactNode;
}) {
  return (
    <div
      className="flex min-h-48 flex-col items-center justify-center gap-2 rounded-lg border border-danger/30 bg-danger-subtle p-8 text-center"
      role="alert"
    >
      <AlertCircle className="size-7 text-danger" aria-hidden />
      <p className="font-medium text-danger">{title}</p>
      {detail && <p className="max-w-md text-sm text-muted-foreground">{detail}</p>}
      {action}
    </div>
  );
}
