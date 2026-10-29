import { Button, Input } from "@/components/Controls";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { ArrowRight, Eye, EyeOff, Loader2, LockKeyhole, ShieldCheck } from "lucide-react";

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
      <section className="relative flex min-h-[360px] flex-col overflow-hidden bg-[#091746] px-7 py-8 text-white sm:px-12 lg:min-h-screen lg:px-16 lg:py-12 xl:px-20">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_85%_55%,rgba(26,105,190,0.25),transparent_55%),linear-gradient(145deg,#08133b,#102a68)]"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-20"
          style={{
            backgroundImage:
              "linear-gradient(rgba(125,190,245,.18) 1px, transparent 1px), linear-gradient(90deg, rgba(125,190,245,.18) 1px, transparent 1px)",
            backgroundSize: "52px 52px",
            maskImage: "linear-gradient(to bottom, transparent 10%, black 90%)",
          }}
        />
        <div className="relative flex items-center gap-5">
          <div className="rounded-xl bg-white px-4 py-3 shadow-lg">
            <img
              src="/banca-mediolanum.svg"
              alt="Banca Mediolanum"
              className="h-auto w-40 sm:w-48"
            />
          </div>
          <div className="hidden h-9 w-px bg-white/20 sm:block" />
          <span className="hidden text-xs font-semibold uppercase tracking-[0.16em] text-blue-100 sm:block">
            Architetture IT
          </span>
        </div>
        <div className="relative z-10 my-12 max-w-xl lg:my-auto lg:py-20">
          <p className="mb-5 text-xs font-semibold uppercase tracking-[0.24em] text-sky-300">
            {t("auth.workspace")}
          </p>
          <h1 className="max-w-xl text-4xl font-semibold leading-[1.1] tracking-tight sm:text-5xl xl:text-6xl">
            {t("auth.heroTitle")}
          </h1>
          <div className="mt-9 flex flex-wrap gap-2 text-xs font-medium text-blue-100/90">
            <span className="rounded-full border border-sky-200/20 bg-white/5 px-3 py-1.5">
              {t("auth.projectsLabel")}
            </span>
            <span className="rounded-full border border-sky-200/20 bg-white/5 px-3 py-1.5">
              {t("auth.suppliersLabel")}
            </span>
            <span className="rounded-full border border-sky-200/20 bg-white/5 px-3 py-1.5">
              {t("auth.resourcesLabel")}
            </span>
          </div>
        </div>
        <svg
          aria-hidden="true"
          viewBox="0 0 680 440"
          fill="none"
          className="pointer-events-none absolute -bottom-20 -right-16 hidden w-[min(75%,600px)] opacity-45 lg:block"
        >
          <g stroke="#70c7ff" strokeWidth="1.3">
            <path d="M55 320 292 182 543 324 305 462Z" />
            <path d="M55 275 292 137 543 279 305 417Z" />
            <path d="M55 230 292 92 543 234 305 372Z" />
            <path d="M55 230v90m237-228v90m251 52v90M305 372v90" />
            <path
              d="m119 193 236-137 192 109M95 348l204 115m-83-325 252 143M160 170l252 143M105 260l237 134m-205-154 237 134"
              opacity=".55"
            />
            <path d="M292 92V30m-22 13 22-13 22 13M543 234l55-32m-8-8 8 8-1 18" />
            <circle cx="292" cy="92" r="5" fill="#70c7ff" />
            <circle cx="543" cy="234" r="5" fill="#70c7ff" />
            <circle cx="55" cy="320" r="5" fill="#70c7ff" />
            <circle cx="305" cy="372" r="5" fill="#70c7ff" />
          </g>
        </svg>
        <p className="relative z-10 text-xs uppercase tracking-[0.16em] text-blue-200/70">
          {t("auth.heroFooter")}
        </p>
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
              className="h-12 w-full rounded-xl bg-[#123a83] px-5 text-sm font-semibold text-white shadow-[0_8px_20px_rgba(55,48,163,0.22)] hover:bg-[#0d2e69] disabled:opacity-60"
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
