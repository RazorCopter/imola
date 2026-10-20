import * as Dialog from "@radix-ui/react-dialog";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { useSession } from "@/features/auth/session";
import { ApiError } from "@/lib/api";

/**
 * Sessione scaduta a lavoro aperto: si rientra senza ricaricare la pagina, quindi filtri,
 * form e bozze restano dove sono. Il modale non è chiudibile a vuoto: senza sessione non
 * si può proseguire, ma nulla viene scartato.
 */
export function SessionExpiredDialog() {
  const { t } = useTranslation();
  const { expired, signIn } = useSession();
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
  } = useForm<{ username: string; password: string }>();

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
    <Dialog.Root open={expired}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 animate-fade-in bg-black/40 backdrop-blur-sm" />
        <Dialog.Content
          onEscapeKeyDown={(event) => event.preventDefault()}
          onPointerDownOutside={(event) => event.preventDefault()}
          className="fixed left-1/2 top-1/2 z-50 w-[min(26rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 animate-slide-up rounded-lg border border-border bg-card p-6 shadow-raised"
        >
          <Dialog.Title className="text-base font-semibold">
            {t("auth.sessionExpiredTitle")}
          </Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-muted-foreground">
            {t("auth.sessionExpiredBody")}
          </Dialog.Description>

          <form onSubmit={(event) => void onSubmit(event)} className="mt-5 space-y-3" noValidate>
            <input
              aria-label={t("auth.username")}
              placeholder={t("auth.username")}
              autoComplete="username"
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              {...register("username", { required: true })}
            />
            <input
              type="password"
              aria-label={t("auth.password")}
              placeholder={t("auth.password")}
              autoComplete="current-password"
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              {...register("password", { required: true })}
            />
            {error !== null && (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}
            <button
              type="submit"
              disabled={isSubmitting}
              className="h-9 w-full rounded-md bg-accent text-sm font-medium text-accent-foreground disabled:opacity-60"
            >
              {t("auth.signInAgain")}
            </button>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
