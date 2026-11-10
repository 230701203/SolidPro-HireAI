import axios, { AxiosError } from "axios";

/**
 * Axios instance. The session is an httpOnly cookie set by the API, so no token is ever
 * readable by (or stored in) JavaScript.
 */
export const api = axios.create({ baseURL: "/api", withCredentials: true });

export interface ApiErrorBody {
  error?: { code?: string; message?: string; fields?: Record<string, string> };
}

// Auth endpoints return 401/403 as a normal part of their flow; only other calls signal "session lost".
const AUTH_FLOW = ["/auth/login", "/auth/register", "/auth/me", "/auth/verify-email", "/auth/logout"];

api.interceptors.response.use(
  (r) => r,
  (err: AxiosError<ApiErrorBody>) => {
    const code = err.response?.data?.error?.code;
    const url = err.config?.url ?? "";
    if (!AUTH_FLOW.some((p) => url.startsWith(p))) {
      if (err.response?.status === 401 && (code === "not_authenticated" || code === "session_expired")) {
        window.dispatchEvent(new Event("auth:expired"));
      }
      if (code === "password_change_required") {
        window.dispatchEvent(new Event("auth:password-change-required"));
      }
    }
    return Promise.reject(err);
  },
);

export function errorCode(err: unknown): string | undefined {
  return axios.isAxiosError<ApiErrorBody>(err) ? err.response?.data?.error?.code : undefined;
}

export function errorMessage(err: unknown, fallback = "Something went wrong. Please try again."): string {
  if (axios.isAxiosError<ApiErrorBody>(err)) {
    if (!err.response) return "Cannot reach the server. Check your connection and try again.";
    return err.response.data?.error?.message ?? fallback;
  }
  return fallback;
}

export function fieldErrors(err: unknown): Record<string, string> {
  return axios.isAxiosError<ApiErrorBody>(err) ? (err.response?.data?.error?.fields ?? {}) : {};
}
