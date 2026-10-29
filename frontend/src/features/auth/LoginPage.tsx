import { Button, Input } from "@/components/Controls";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { ArrowRight, Eye, EyeOff, Layers3, Loader2, LockKeyhole, ShieldCheck } from "lucide-react";

import { useSession } from "@/features/auth/session";
import { ApiError } from "@/lib/api";

interface Credentials {
  username: string;
  password: string;
}

export function LoginPage() {
  const { t } = useTranslation();
  const { signIn } = useSession();
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
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
    <main className="min-h-screen bg-[#f3f5f9] text-[#17213a] lg:grid lg:grid-cols-[minmax(0,1.05fr)_minmax(480px,0.95fr)]">
      <section className="relative flex min-h-[300px] flex-col overflow-hidden bg-[#111b35] px-7 py-8 text-white sm:px-12 lg:min-h-screen lg:px-16 lg:py-12 xl:px-24">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_15%_90%,rgba(91,82,221,0.32),transparent_45%),radial-gradient(ellipse_at_90%_10%,rgba(65,110,190,0.2),transparent_40%)]"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-44 -right-28 size-[480px] rounded-full border border-white/10 lg:size-[680px]"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-32 -right-16 size-[380px] rounded-full border border-white/10 lg:size-[540px]"
        />
        <div className="relative flex items-center gap-3">
          <span className="flex size-11 items-center justify-center rounded-xl bg-white text-[#28366c] shadow-lg">
            <Layers3 className="size-6" aria-hidden />
          </span>
          <div>
            <p className="text-base font-semibold tracking-tight">{t("app.name")}</p>
            <p className="text-xs text-slate-300">Imola Informatica</p>
          </div>
        </div>
        <div className="relative my-12 max-w-xl lg:my-auto lg:py-16">
          <p className="mb-5 text-xs font-semibold uppercase tracking-[0.22em] text-indigo-300">
            {t("auth.workspace")}
          </p>
          <h1 className="max-w-lg text-4xl font-semibold leading-[1.12] tracking-tight sm:text-5xl xl:text-6xl">
            {t("auth.heroTitle")}
          </h1>
          <p className="mt-6 max-w-md text-base leading-7 text-slate-300 sm:text-lg">
            {t("auth.heroDescription")}
          </p>
          <div className="mt-10 hidden h-px w-16 bg-indigo-400 lg:block" />
        </div>
        <p className="relative hidden text-xs text-slate-400 lg:block">{t("auth.heroFooter")}</p>
      </section>

      <section className="flex items-center justify-center px-6 py-12 sm:px-12 lg:px-16">
        <div className="w-full max-w-[420px]">
          <div className="mb-9 flex size-12 items-center justify-center rounded-2xl bg-indigo-100 text-indigo-700">
            <LockKeyhole className="size-5" aria-hidden />
          </div>
          <p className="mb-3 text-xs font-semibold uppercase tracking-[0.2em] text-indigo-600">
            {t("auth.reservedArea")}
          </p>
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">{t("auth.welcome")}</h2>
          <p className="mt-3 text-sm leading-6 text-slate-500">{t("auth.instructions")}</p>

          <form onSubmit={(event) => void onSubmit(event)} className="mt-9 space-y-5" noValidate>
            <div className="space-y-2">
              <label htmlFor="username" className="text-sm font-semibold text-slate-700">
                {t("auth.username")}
              </label>
              <Input
                id="username"
                autoComplete="username"
                autoFocus
                className="h-12 w-full rounded-xl border-slate-300 bg-white px-4 text-slate-900 shadow-sm focus:border-indigo-500"
                {...register("username", { required: true })}
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="password" className="text-sm font-semibold text-slate-700">
                {t("auth.password")}
              </label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  className="h-12 w-full rounded-xl border-slate-300 bg-white px-4 pr-12 text-slate-900 shadow-sm focus:border-indigo-500"
                  {...register("password", { required: true })}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={t(showPassword ? "auth.hidePassword" : "auth.showPassword")}
                  aria-pressed={showPassword}
                  className="absolute inset-y-0 right-0 flex w-12 items-center justify-center rounded-xl text-slate-500 hover:text-indigo-700"
                >
                  {showPassword ? (
                    <EyeOff className="size-5" aria-hidden />
                  ) : (
                    <Eye className="size-5" aria-hidden />
                  )}
                </button>
              </div>
            </div>
            {error !== null && (
              <p role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">
                {error}
              </p>
            )}
            <Button
              type="submit"
              disabled={isSubmitting}
              className="h-12 w-full rounded-xl bg-[#3730a3] px-5 text-sm font-semibold text-white shadow-[0_8px_20px_rgba(55,48,163,0.22)] hover:bg-[#312e81] disabled:opacity-60"
            >
              {isSubmitting ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
              {t("auth.signIn")}
              {!isSubmitting && <ArrowRight className="ml-1 size-4" aria-hidden />}
            </Button>
          </form>
          <div className="mt-9 flex items-center gap-2 border-t border-slate-200 pt-6 text-xs leading-5 text-slate-500">
            <ShieldCheck className="size-4 shrink-0 text-indigo-500" aria-hidden />
            {t("auth.accessNote")}
          </div>
        </div>
      </section>
    </main>
  );
}
