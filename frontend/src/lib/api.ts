/**
 * Client HTTP.
 *
 * Scelta deliberata: nessun interceptor che esegue il logout sui 401. Quando la sessione
 * scade il server risponde con problem+json e `code: "session_expired"`: il client alza un
 * evento, la app mostra un modale di re-login e la richiesta fallita viene ritentata, così
 * il lavoro in corso (form aperti, filtri, bozze) non va perso.
 */

export const API_BASE: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api/v1";

export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  code: string;
  detail?: string | null;
  instance?: string | null;
  errors?: { campo: string; messaggio: string }[];
}

export class ApiError extends Error {
  readonly problem: ProblemDetail;
  readonly status: number;

  constructor(problem: ProblemDetail) {
    super(problem.detail || problem.title);
    this.name = "ApiError";
    this.problem = problem;
    this.status = problem.status;
  }

  get code(): string {
    return this.problem.code;
  }

  /** Errori campo per campo, pronti per react-hook-form. */
  get fieldErrors(): Record<string, string> {
    const result: Record<string, string> = {};
    for (const item of this.problem.errors ?? []) {
      result[item.campo] = item.messaggio;
    }
    return result;
  }
}

export class SessionExpiredError extends ApiError {}
export class StaleResourceError extends ApiError {}

type Listener = () => void;
const sessionExpiredListeners = new Set<Listener>();

export function onSessionExpired(listener: Listener): () => void {
  sessionExpiredListeners.add(listener);
  return () => sessionExpiredListeners.delete(listener);
}

function notifySessionExpired(): void {
  for (const listener of sessionExpiredListeners) listener();
}

function readCookie(name: string): string {
  const match = document.cookie.match(new RegExp(`(^|;\\s*)${name}=([^;]*)`));
  return match?.[2] ? decodeURIComponent(match[2]) : "";
}

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** ETag della risorsa, per il lock ottimistico (If-Match). */
  ifMatch?: string;
  /** Risposte 401 attese (es. il login): non alzano il modale di sessione scaduta. */
  expectUnauthorized?: boolean;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, ifMatch, expectUnauthorized, headers, ...rest } = options;
  const method = (rest.method ?? "GET").toUpperCase();

  const requestHeaders = new Headers(headers);
  requestHeaders.set("Accept", "application/json, application/problem+json");
  if (body !== undefined && !(body instanceof FormData)) {
    requestHeaders.set("Content-Type", "application/json");
  }
  if (UNSAFE_METHODS.has(method)) {
    requestHeaders.set("X-CSRFToken", readCookie("sl_csrftoken"));
  }
  if (ifMatch) {
    requestHeaders.set("If-Match", ifMatch);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...rest,
    method,
    credentials: "same-origin",
    headers: requestHeaders,
    body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("Content-Type") ?? "";
  const payload: unknown = contentType.includes("json")
    ? await (response.json() as Promise<unknown>)
    : await response.text();

  if (response.ok) {
    return payload as T;
  }

  const fallbackDetail =
    typeof payload === "string"
      ? payload
      : typeof payload === "object" && payload !== null
        ? typeof (payload as Record<string, unknown>).detail === "string"
          ? ((payload as Record<string, unknown>).detail as string)
          : typeof (payload as Record<string, unknown>).message === "string"
            ? ((payload as Record<string, unknown>).message as string)
            : null
        : null;

  const fallbackTitle =
    typeof payload === "object" &&
    payload !== null &&
    typeof (payload as Record<string, unknown>).title === "string"
      ? ((payload as Record<string, unknown>).title as string)
      : (fallbackDetail ?? "Errore inatteso");

  const problem: ProblemDetail =
    typeof payload === "object" && payload !== null && "status" in payload
      ? (payload as ProblemDetail)
      : {
          type: "about:blank",
          title: fallbackTitle,
          status: response.status,
          code: `http-${response.status}`,
          detail: fallbackDetail,
        };

  if (response.status === 401 && !expectUnauthorized) {
    notifySessionExpired();
    throw new SessionExpiredError(problem);
  }
  if (response.status === 412 || response.status === 428) {
    throw new StaleResourceError(problem);
  }
  throw new ApiError(problem);
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "POST", body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PUT", body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PATCH", body }),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "DELETE" }),
};
