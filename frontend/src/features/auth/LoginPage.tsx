import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Loader2, LockKeyhole } from "lucide-react";

import { useSession } from "@/features/auth/session";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Credentials {
  username: string;
  password: string;
}

export function LoginPage() {
  const { t } = useTranslation();
  const { signIn } = useSession();
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<Credentials>({ defaultValues: { username: "", password: "" } });

  const onSubmit = handleSubmit(async ({ username, password }) => {
    setError(null);
    try {
      await signIn(username, password);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? (caught.problem.detail ?? t("auth.invalidCredentials"))
          : t("errors.network"),
      );
    }
  });

  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/40 px-4">
      <div className="w-full max-w-sm animate-slide-up rounded-lg border border-border bg-card p-8 shadow-raised">
        <div className="mb-6 flex items-center gap-3">
          <span className="flex size-9 items-center justify-center rounded-md bg-accent text-accent-foreground">
            <LockKeyhole className="size-5" aria-hidden />
          </span>
          <div>
            <h1 className="text-base font-semibold leading-tight">{t("app.name")}</h1>
            <p className="text-xs text-muted-foreground">{t("app.subtitle")}</p>
          </div>
        </div>

        <form onSubmit={(event) => void onSubmit(event)} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <label htmlFor="username" className="text-sm font-medium">
              {t("auth.username")}
            </label>
            <input
              id="username"
              autoComplete="username"
              autoFocus
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              {...register("username", { required: true })}
            />
          </div>

          <div className="space-y-1.5">
            <label htmlFor="password" className="text-sm font-medium">
              {t("auth.password")}
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              {...register("password", { required: true })}
            />
          </div>

          {error !== null && (
            <p role="alert" className="rounded-md bg-danger-subtle px-3 py-2 text-sm text-danger">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className={cn(
              "flex h-9 w-full items-center justify-center gap-2 rounded-md bg-accent text-sm",
              "font-medium text-accent-foreground transition hover:opacity-90 disabled:opacity-60",
            )}
          >
            {isSubmitting && <Loader2 className="size-4 animate-spin" aria-hidden />}
            {t("auth.signIn")}
          </button>
        </form>
      </div>
    </main>
  );
}
