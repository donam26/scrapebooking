/**
 * Client HTTP có kiểu cho backend FastAPI, đi qua proxy cùng origin `/api/...`.
 *
 * - Ném `ApiError` (status + detail) khi response không ok.
 * - 401 -> xoá cookie (best-effort) và chuyển về /login.
 * - Operator: tự gắn `tenant_id` vào mọi endpoint theo tenant khi đã chọn tenant.
 */
import type { components } from "./api-types";
import { fieldLabel, translateError } from "./errors";

export type Schemas = components["schemas"];
export type UserOut = Schemas["UserOut"];
export type TenantOut = Schemas["TenantOut"];
export type TenantUpdate = Schemas["TenantUpdate"];
export type TenantCreate = Schemas["TenantCreate"];
export type UserCreate = Schemas["UserCreate"];
export type UserUpdate = Schemas["UserUpdate"];
export type WatchItemOut = Schemas["WatchItemOut"];
export type WatchItemCreate = Schemas["WatchItemCreate"];
export type WatchItemUpdate = Schemas["WatchItemUpdate"];
export type OverviewOut = Schemas["OverviewOut"];
export type HotelRow = Schemas["HotelRow"];
export type DateCell = Schemas["DateCell"];
export type CompsetDayOut = Schemas["CompsetDayOut"];
export type HotelDetailOut = Schemas["HotelDetailOut"];
export type DayDetailOut = Schemas["DayDetailOut"];
export type RoomSnapshotOut = Schemas["RoomSnapshotOut"];
export type RoomTypeOut = Schemas["RoomTypeOut"];
export type HotelDateSnapshotOut = Schemas["HotelDateSnapshotOut"];
export type EventOut = Schemas["EventOut"];
export type ScanRunOut = Schemas["ScanRunOut"];
export type InsightOut = Schemas["InsightOut"];
export type InsightDetailOut = Schemas["InsightDetailOut"];
export type MappingOut = Schemas["MappingOut"];
export type PreviewOut = Schemas["PreviewOut"];
export type PmsImportOut = Schemas["PmsImportOut"];
export type OwnDailyOut = Schemas["OwnDailyOut"];
export type HealthSummaryOut = Schemas["HealthSummaryOut"];
export type ScrapeSessionOut = Schemas["ScrapeSessionOut"];
export type ValidationErrorItem = Schemas["ValidationError"];

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(detailToMessage(detail, status));
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Chuyển `detail` của FastAPI (chuỗi hoặc mảng lỗi validation) thành câu đọc được. */
export function detailToMessage(detail: unknown, status?: number): string {
  if (typeof detail === "string" && detail) return translateError(detail);
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          const v = item as ValidationErrorItem;
          const loc = (v.loc ?? [])
            .filter((p) => p !== "body" && p !== "query")
            .map((p) => fieldLabel(String(p)))
            .join(".");
          const msg = translateError(v.msg);
          return loc ? `${loc}: ${msg}` : msg;
        }
        return String(item);
      })
      .filter(Boolean);
    if (parts.length) return parts.join("; ");
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  if (status === 401) return "Phiên đăng nhập hết hạn";
  if (status === 403) return "Bạn không có quyền thực hiện thao tác này";
  if (status === 404) return "Không tìm thấy dữ liệu";
  if (status === 502) return "Không kết nối được API";
  return status ? `Lỗi HTTP ${status}` : "Lỗi không xác định";
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return translateError(err.message);
  return translateError(String(err));
}

// ---- phạm vi tenant (operator) ----

let scope: { isOperator: boolean; tenantId: number | null } = { isOperator: false, tenantId: null };

export function setApiTenantScope(next: { isOperator: boolean; tenantId: number | null }): void {
  scope = next;
}

/** Endpoint không nhận tenant_id (auth, quản trị operator, health, users). */
const TENANT_FREE = ["/auth", "/tenants", "/health", "/healthz", "/users"];

function isTenantScoped(path: string): boolean {
  return !TENANT_FREE.some((p) => path === p || path.startsWith(`${p}/`));
}

// ---- request lõi ----

export type Query = Record<string, string | number | boolean | null | undefined>;

type RequestOptions = {
  query?: Query;
  body?: unknown;
  form?: FormData;
  /** Trả text thay vì JSON. */
  text?: boolean;
  /** Không chuyển về /login khi 401 (dùng cho chính form đăng nhập). */
  noAuthRedirect?: boolean;
};

function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v === undefined || v === null || v === "") continue;
    params.set(k, String(v));
  }
  if (scope.isOperator && scope.tenantId !== null && isTenantScoped(path) && !params.has("tenant_id")) {
    params.set("tenant_id", String(scope.tenantId));
  }
  const qs = params.toString();
  return `/api${path}${qs ? `?${qs}` : ""}`;
}

let redirecting = false;

function redirectToLogin(): void {
  if (typeof window === "undefined" || redirecting) return;
  redirecting = true;
  const next = window.location.pathname + window.location.search;
  // Xoá cookie cũ để proxy không giữ người dùng ở trang cần đăng nhập.
  fetch("/api/auth/logout", { method: "POST", credentials: "include" })
    .catch(() => undefined)
    .finally(() => {
      const url = new URL("/login", window.location.origin);
      if (next && next !== "/" && !next.startsWith("/login")) url.searchParams.set("next", next);
      window.location.assign(url.toString());
    });
}

async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: opts.text ? "text/plain" : "application/json" };
  let body: BodyInit | undefined;
  if (opts.form) {
    body = opts.form;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(buildUrl(path, opts.query), {
    method,
    headers,
    body,
    credentials: "include",
    cache: "no-store",
  });
  if (res.status === 401 && !opts.noAuthRedirect) {
    redirectToLogin();
    throw new ApiError(401, "Phiên đăng nhập hết hạn");
  }
  if (!res.ok) {
    let detail: unknown = null;
    const ct = res.headers.get("content-type") ?? "";
    try {
      detail = ct.includes("application/json") ? (await res.json())?.detail : await res.text();
    } catch {
      detail = null;
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  if (opts.text) return (await res.text()) as T;
  return (await res.json()) as T;
}

// ---- endpoint có kiểu ----

export const api = {
  auth: {
    login: (body: Schemas["LoginRequest"]) =>
      request<UserOut>("POST", "/auth/login", { body, noAuthRedirect: true }),
    logout: () => request<void>("POST", "/auth/logout", { noAuthRedirect: true }),
    me: () => request<UserOut>("GET", "/auth/me", { noAuthRedirect: true }),
  },
  tenants: {
    list: () => request<TenantOut[]>("GET", "/tenants"),
    get: (id: number) => request<TenantOut>("GET", `/tenants/${id}`),
    create: (body: TenantCreate) => request<TenantOut>("POST", "/tenants", { body }),
    update: (id: number, body: TenantUpdate) => request<TenantOut>("PATCH", `/tenants/${id}`, { body }),
  },
  settings: {
    get: () => request<TenantOut>("GET", "/settings"),
    update: (body: TenantUpdate) => request<TenantOut>("PATCH", "/settings", { body }),
  },
  users: {
    list: () => request<UserOut[]>("GET", "/users"),
    create: (body: UserCreate) => request<UserOut>("POST", "/users", { body }),
    update: (id: number, body: UserUpdate) => request<UserOut>("PATCH", `/users/${id}`, { body }),
  },
  watchlist: {
    list: (includeInactive = false) =>
      request<WatchItemOut[]>("GET", "/watchlist", { query: { include_inactive: includeInactive } }),
    add: (body: WatchItemCreate) => request<WatchItemOut>("POST", "/watchlist", { body }),
    update: (hotelId: number, body: WatchItemUpdate) =>
      request<WatchItemOut>("PATCH", `/watchlist/${hotelId}`, { body }),
    remove: (hotelId: number) => request<void>("DELETE", `/watchlist/${hotelId}`),
    /** Quét ngay toàn bộ watchlist của tenant (202; trong 10 phút trả về đợt đang chạy). */
    scanNow: () => request<ScanRunOut>("POST", "/watchlist/scan-now"),
  },
  overview: (query: { start?: string; end?: string }) => request<OverviewOut>("GET", "/overview", { query }),
  hotel: (hotelId: number, query: { start?: string; end?: string; event_limit?: number }) =>
    request<HotelDetailOut>("GET", `/hotels/${hotelId}`, { query }),
  day: (hotelId: number, stayDate: string, historyDays = 14) =>
    request<DayDetailOut>("GET", `/hotels/${hotelId}/dates/${stayDate}`, {
      query: { history_days: historyDays },
    }),
  events: (query: {
    hotel_id?: number | null;
    event_type?: string | null;
    stay_from?: string | null;
    stay_to?: string | null;
    observed_since?: string | null;
    limit?: number;
    offset?: number;
  }) => request<EventOut[]>("GET", "/events", { query }),
  runs: (limit = 10) => request<ScanRunOut[]>("GET", "/runs", { query: { limit } }),
  insights: {
    list: (limit = 30) => request<InsightOut[]>("GET", "/insights", { query: { limit } }),
    get: (id: number) => request<InsightDetailOut>("GET", `/insights/${id}`),
    generate: () => request<InsightOut>("POST", "/insights/generate"),
  },
  pms: {
    template: () => request<string>("GET", "/pms/template", { text: true }),
    getMapping: (adapter = "csv") => request<MappingOut>("GET", "/pms/mapping", { query: { adapter } }),
    putMapping: (body: Schemas["MappingIn"]) => request<MappingOut>("PUT", "/pms/mapping", { body }),
    preview: (file: File, adapter = "csv") => {
      const form = new FormData();
      form.append("file", file);
      form.append("adapter", adapter);
      return request<PreviewOut>("POST", "/pms/preview", { form });
    },
    import: (file: File, hotelId: number, adapter = "csv") => {
      const form = new FormData();
      form.append("file", file);
      form.append("hotel_id", String(hotelId));
      form.append("adapter", adapter);
      return request<PmsImportOut>("POST", "/pms/import", { form });
    },
    imports: (limit = 20) => request<PmsImportOut[]>("GET", "/pms/imports", { query: { limit } }),
    daily: (hotelId?: number | null, limit = 120) =>
      request<OwnDailyOut[]>("GET", "/pms/daily", { query: { hotel_id: hotelId, limit } }),
  },
  health: {
    summary: () => request<HealthSummaryOut>("GET", "/health/summary"),
    runs: (limit = 20) => request<ScanRunOut[]>("GET", "/health/runs", { query: { limit } }),
    sessions: (limit = 50) => request<ScrapeSessionOut[]>("GET", "/health/sessions", { query: { limit } }),
    /** Operator: quét ngay mọi tenant đang hoạt động. */
    scanNow: () => request<ScanRunOut>("POST", "/health/scan-now"),
  },
};
