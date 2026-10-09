/**
 * Client HTTP có kiểu cho backend FastAPI, đi qua proxy cùng origin `/api/...`.
 *
 * - Ném `ApiError` (status + detail) khi response không ok.
 * - 401 -> xoá cookie (best-effort) và chuyển về /login.
 * - Operator: tự gắn `tenant_id` vào mọi endpoint theo tenant khi đã chọn tenant.
 */
import type { components } from "./api-types";

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
export type NotificationSettingsOut = Schemas["NotificationSettingsOut"];
export type NotificationRuleOut = Schemas["NotificationRuleOut"];
export type NotificationLogOut = Schemas["NotificationLogOut"];
export type RecipientOut = Schemas["RecipientOut"];
export type MarketPaceOut = Schemas["MarketPaceOut"];
export type PaceNightOut = Schemas["PaceNightOut"];
export type SuggestionOut = Schemas["SuggestionOut"];
export type HotelOut = Schemas["HotelOut"];
export type ListingOut = Schemas["ListingOut"];
export type ChannelOut = Schemas["ChannelOut"];
export type RateDetailOut = Schemas["RateDetailOut"];
export type HolidayOut = Schemas["HolidayOut"];
export type WeatherOut = Schemas["WeatherOut"];
export type RunJobOut = Schemas["RunJobOut"];
export type MarketOccupancyOut = Schemas["MarketOccupancyOut"];
export type HotelOccOut = Schemas["HotelOccOut"];
export type LocalEventOut = Schemas["LocalEventOut"];
export type LocalEventIn = Schemas["LocalEventIn"];
export type DestinationOut = Schemas["DestinationOut"];
export type MarketAreaOut = Schemas["MarketAreaOut"];
export type MarketAreaCreate = Schemas["MarketAreaCreate"];
export type MarketAreaUpdate = Schemas["MarketAreaUpdate"];
export type MarketCityOut = Schemas["MarketCityOut"];
export type CityHotelOut = Schemas["CityHotelOut"];
export type CityHotelsOut = Schemas["CityHotelsOut"];
export type DataStatusOut = Schemas["DataStatusOut"];
export type CompsetReviewOut = Schemas["CompsetReviewOut"];
export type CalibrationOut = Schemas["CalibrationOut"];
export type LeadCalibrationOut = Schemas["LeadCalibrationOut"];
// ---- Phase 3: thông báo qua email/Zalo/webhook, đăng ký theo người, đo lượt nhấn/"Đã xử lý" ----
export type NotificationKind = Schemas["NotificationKind"];
export type SubscriptionIn = Schemas["SubscriptionIn"];
export type SubscriptionOut = Schemas["SubscriptionOut"];
/** Kênh gửi tin: email | zalo (ZNS) | webhook. */
export type NotifyChannel = SubscriptionIn["channel"];
/** Nhóm tin của một đăng ký: alerts | daily_insight | weekly_report | data_stale (rỗng = mọi loại). */
export type SubscriptionKind = SubscriptionIn["kinds"][number];
export type EngagementOut = Schemas["EngagementOut"];
export type EngagementWeekOut = Schemas["EngagementWeekOut"];
// ---- Phase 4: radar cạnh tranh ----
export type PromotionsOut = Schemas["PromotionsOut"];
export type HotelPromosOut = Schemas["HotelPromosOut"];
export type PromoRunOut = Schemas["PromoRunOut"];
export type PromoNightOut = Schemas["PromoNightOut"];
export type RestrictionsOut = Schemas["RestrictionsOut"];
export type HotelRestrictionsOut = Schemas["HotelRestrictionsOut"];
export type RestrictionNightOut = Schemas["RestrictionNightOut"];
export type CancellationsOut = Schemas["CancellationsOut"];
export type CancellationOut = Schemas["CancellationOut"];
export type AreaScarcityOut = Schemas["AreaScarcityOut"];
export type AreaNightOut = Schemas["AreaNightOut"];
// ---- Phase 5: OTB và KPI thật ----
export type OtbImportOut = Schemas["OtbImportOut"];
/** "otb_report" = báo cáo phòng đã đặt theo ngày; "bookings" = file đặt phòng chi tiết. */
export type OtbImportKind = Schemas["Body_import_otb_pms_otb_import_post"]["kind"];
export type OtbOut = Schemas["OtbOut"];
export type OtbNightOut = Schemas["OtbNightOut"];
export type KpiOut = Schemas["KpiOut"];
// ---- Phase 6: RMS-lite ----
export type StrategyIn = Schemas["StrategyIn"];
export type StrategyOut = Schemas["StrategyOut"];
export type ReasonOut = Schemas["ReasonOut"];
export type DecisionIn = Schemas["DecisionIn"];
export type OutcomesOut = Schemas["OutcomesOut"];
export type OutcomeNightOut = Schemas["OutcomeNightOut"];
export type BacktestOut = Schemas["BacktestOut"];
// ---- Phase 7: uy tín, hiển thị ----
export type ReputationOut = Schemas["ReputationOut"];
export type ReputationHotelOut = Schemas["ReputationHotelOut"];
export type VisibilityOut = Schemas["VisibilityOut"];
export type VisibilityHotelOut = Schemas["VisibilityHotelOut"];

/** Thị trường nguồn của khách (lễ của các nước này hiện trên lịch), khớp `holidays/data.py` SOURCE_MARKETS. */
export const SOURCE_MARKETS = ["cn", "kr", "jp", "tw", "ru", "in", "us", "au"] as const;
export type SourceMarket = (typeof SOURCE_MARKETS)[number];

/** Giá đem so (cùng điều kiện): mọi gói | hoàn huỷ | có bữa sáng | chỉ phòng. */
export type PriceBasis = Schemas["PriceBasis"];
/** Kiểu ngày lễ: Tết, lễ, cầu du lịch, lễ thị trường nguồn (Chuseok, Tuần lễ Vàng…), mùa (nghỉ hè). */
export type HolidayKind = HolidayOut["kind"];

/**
 * Năm trạng thái một ô khách sạn × đêm (`DateCell.state`, roadmap 2.7). `restricted` = bán được ở
 * điều kiện khác (số đêm tối thiểu, đóng ngày đến), KHÔNG phải hết phòng.
 */
export type CellState = "available" | "sold_out" | "restricted" | "no_price" | "error";
const CELL_STATES: readonly string[] = ["available", "sold_out", "restricted", "no_price", "error"];

/** Trạng thái của ô: `state` mới; dữ liệu cũ chưa có `state` thì suy từ `availability_status`. */
export function cellState(c: Pick<DateCell, "state" | "availability_status"> | null | undefined): CellState | null {
  if (!c) return null;
  if (c.state && CELL_STATES.includes(c.state)) return c.state as CellState;
  switch (c.availability_status) {
    case "available":
      return "available";
    case "sold_out":
      return "sold_out";
    case "restricted":
      return "restricted";
    case "unknown":
      return "error";
    default:
      return null;
  }
}

/** Gói rẻ nhất trên Booking.com của một đêm (`RateDetailOut.cheapest_rate`). */
export type CheapestRate = {
  price: string | null;
  /** Khoá gói "t|f" = hoàn huỷ | bữa sáng (t/f/?). */
  key: string | null;
  refundable: boolean | null;
  breakfast: boolean | null;
  /** Giá trước KM (giá gạch). */
  price_original: string | null;
  promo_label: string | null;
  /** Nguồn bán lại (dòng "Partner offer" của Booking.com). */
  source_supplier: string | null;
  taxes_included: boolean | null;
  room_type_id: number | null;
};

function str(v: unknown): string | null {
  if (v === null || v === undefined || v === "") return null;
  return typeof v === "string" ? v : typeof v === "number" ? String(v) : null;
}

function bool(v: unknown): boolean | null {
  return typeof v === "boolean" ? v : null;
}

export function cheapestRate(c: Pick<RateDetailOut, "cheapest_rate">): CheapestRate | null {
  const r = c.cheapest_rate;
  if (!r) return null;
  return {
    price: str(r.price),
    key: str(r.key),
    refundable: bool(r.refundable),
    breakfast: bool(r.breakfast),
    price_original: str(r.price_original),
    promo_label: str(r.promo_label),
    source_supplier: str(r.source_supplier),
    taxes_included: bool(r.taxes_included),
    room_type_id: typeof r.room_type_id === "number" ? r.room_type_id : null,
  };
}

/** Nhãn KM của promo_start (`detail.labels`: nhãn → độ sâu %) / promo_end (`detail.labels`: mảng nhãn). */
export function promoLabels(e: Pick<EventOut, "detail" | "from_value" | "to_value" | "event_type">): Array<{ label: string; depth: string | null }> {
  const raw = e.detail?.labels;
  if (Array.isArray(raw)) return raw.filter((x): x is string => typeof x === "string").map((label) => ({ label, depth: null }));
  if (raw && typeof raw === "object") return Object.entries(raw as Record<string, unknown>).map(([label, depth]) => ({ label, depth: str(depth) }));
  const text = e.event_type === "promo_end" ? e.from_value : e.to_value;
  return (text ?? "").split(",").map((x) => x.trim()).filter(Boolean).map((label) => ({ label, depth: null }));
}

/** Thao tác trên trang Booking.com (listing) của khách sạn: tạm dừng, quét lại, kiểm tra lại. */
export type ListingAction = "pause" | "resume" | "retry";

/**
 * Lỗi HTTP từ backend. `message` giữ thông điệp gốc (tiếng Anh, cho log); câu hiển thị theo ngôn
 * ngữ lấy bằng `useErrorMessage()` (lib/errors.ts) lúc render.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" && detail ? detail : `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

// ---- phạm vi tenant (operator) ----

let scope: { isOperator: boolean; tenantId: number | null } = { isOperator: false, tenantId: null };

export function setApiTenantScope(next: { isOperator: boolean; tenantId: number | null }): void {
  scope = next;
}

/** Endpoint không nhận tenant_id (auth, quản trị operator, health, users). */
const TENANT_FREE = ["/auth", "/tenants", "/health", "/healthz", "/users", "/channels"];

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

/** Đường dẫn qua proxy `/api` (kèm `tenant_id` cho operator), dùng cho liên kết tải tệp. */
export function apiUrl(path: string, query?: Query): string {
  return buildUrl(path, query);
}

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
    throw new ApiError(401, "not authenticated");
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
    scanNow: () => request<ScanRunOut[]>("POST", "/watchlist/scan-now"),
    /** Quét ngay một khách sạn trong watchlist (một lượt nhỏ). */
    scanHotel: (hotelId: number) => request<ScanRunOut[]>("POST", `/watchlist/${hotelId}/scan-now`),
    /** Thay URL Booking.com của khách sạn đã theo dõi (đường dẫn hỏng hoặc dán nhầm). */
    addListing: (hotelId: number, url: string) =>
      request<ListingOut>("POST", `/watchlist/${hotelId}/listings`, { body: { url } }),
    /** Tạm dừng, quét lại hoặc kiểm tra lại trang Booking.com của khách sạn. */
    listingAction: (hotelId: number, listingId: number, action: ListingAction) =>
      request<ListingOut | null>("PATCH", `/watchlist/${hotelId}/listings/${listingId}`, { body: { action } }),
    /** Rà soát compset của một khách sạn của bạn theo quy tắc CoStar STR (≥4 đối thủ, ≤50% số phòng, rà soát 2 lần/năm). */
    compsetReview: (ownHotelId?: number | null) =>
      request<CompsetReviewOut>("GET", "/watchlist/compset-review", { query: { own_hotel_id: ownHotelId } }),
  },
  channels: () => request<ChannelOut[]>("GET", "/channels"),
  overview: (query: { start?: string; end?: string; price_basis?: PriceBasis; own_hotel_id?: number | null }) =>
    request<OverviewOut>("GET", "/overview", { query }),
  /** Dữ liệu Booking.com mới nhất (quan sát thành công cuối cùng) và tỷ lệ thành công 7 ngày (SLA). */
  dataStatus: () => request<DataStatusOut>("GET", "/data-status"),
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
  /** Từng khách sạn của tenant trong một lượt quét. */
  runJobs: (runId: number) => request<RunJobOut[]>("GET", `/runs/${runId}/jobs`),
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
    /** OTB theo ngày (Phase 5): nhập báo cáo phòng đã đặt hoặc file đặt phòng chi tiết. Chỉ người được ghi. */
    otb: {
      /** CSV mẫu cho từng loại tệp. */
      template: (kind: OtbImportKind = "otb_report") =>
        request<string>("GET", "/pms/otb/template", { query: { kind }, text: true }),
      import: (args: { file: File; hotelId: number; kind: OtbImportKind; asOfDate?: string | null; roomsAvailable?: number | null }) => {
        const form = new FormData();
        form.append("file", args.file);
        form.append("hotel_id", String(args.hotelId));
        form.append("kind", args.kind);
        if (args.asOfDate) form.append("as_of_date", args.asOfDate);
        if (args.roomsAvailable !== null && args.roomsAvailable !== undefined) form.append("rooms_available", String(args.roomsAvailable));
        return request<OtbImportOut>("POST", "/pms/otb/import", { form });
      },
    },
  },
  market: {
    /** Nhịp và chỉ báo lấp đầy trên Booking.com cho một khách sạn của bạn. */
    pace: (query: { start?: string; end?: string; own_hotel_id?: number | null }) =>
      request<MarketPaceOut>("GET", "/market/pace", { query }),
    /**
     * Ghi nhận đã áp dụng/bỏ qua gợi ý. `appliedPrice`: giá thật sự đã đặt (khi khác giá mục tiêu),
     * để đo kết quả sau đêm lưu trú; bỏ trống thì backend lấy giá mục tiêu.
     */
    decide: (stayDate: string, kind: SuggestionOut["kind"], decision: DecisionIn["decision"], appliedPrice?: number | null) =>
      request<SuggestionOut>("PUT", `/market/suggestions/${stayDate}/${kind}`, {
        body: { decision, ...(appliedPrice ? { applied_price: appliedPrice } : {}) } satisfies DecisionIn,
      }),
    undo: (stayDate: string, kind: string) => request<void>("DELETE", `/market/suggestions/${stayDate}/${kind}`),
    /** Chiến lược giá của khách sạn của bạn (Phase 6); 404 khi tenant chưa có khách sạn vai trò "self". */
    strategy: {
      get: (ownHotelId?: number | null) => request<StrategyOut>("GET", "/market/strategy", { query: { own_hotel_id: ownHotelId } }),
      put: (body: StrategyIn, ownHotelId?: number | null) =>
        request<StrategyOut>("PUT", "/market/strategy", { body, query: { own_hotel_id: ownHotelId } }),
    },
    /** Nhật ký "gợi ý đã áp dụng → kết quả" và tỷ lệ áp dụng (mặc định 60 ngày). */
    outcomes: (query: { days?: number; own_hotel_id?: number | null } = {}) =>
      request<OutcomesOut>("GET", "/market/suggestions/outcomes", { query }),
    /** Chạy lại luật gợi ý trên giá đối thủ `lead` ngày trước mỗi đêm đã qua, so với công suất thật. */
    backtest: (query: { days?: number; lead?: number; own_hotel_id?: number | null } = {}) =>
      request<BacktestOut>("GET", "/market/suggestions/backtest", { query }),
    /** OTB, pickup, pace (4 tuần trước, STLY), dự báo theo đêm và KPI PMS (Occ/ADR/RevPAR). */
    otb: (query: { start?: string; end?: string; own_hotel_id?: number | null; days?: number }) =>
      request<OtbOut>("GET", "/market/otb", { query }),
    /** Radar cạnh tranh (Phase 4) từ dữ liệu Booking.com đã quét: tối đa 120 đêm. */
    radar: {
      promotions: (query: { start?: string; end?: string }) =>
        request<PromotionsOut>("GET", "/market/radar/promotions", { query }),
      restrictions: (query: { start?: string; end?: string }) =>
        request<RestrictionsOut>("GET", "/market/radar/restrictions", { query }),
      cancellation: (query: { start?: string; end?: string }) =>
        request<CancellationsOut>("GET", "/market/radar/cancellation", { query }),
      /** Số chỗ ở còn phòng của khu vực theo đêm; 404 khi tenant chưa có khu vực thị trường. */
      areaScarcity: (query: { area_id?: number | null; start?: string; end?: string }) =>
        request<AreaScarcityOut>("GET", "/market/radar/area-scarcity", { query }),
    },
    /** Điểm, số review, tốc độ review/tháng, mốc điểm kế tiếp, chỉ số giá–điểm (Booking.com). */
    reputation: (query: { days?: number } = {}) => request<ReputationOut>("GET", "/market/reputation", { query }),
    /** Thứ hạng trên trang kết quả của khu vực (tách thẻ quảng cáo) và huy hiệu; rỗng khi chưa có khu vực/lượt quét. */
    visibility: (query: { days?: number; area_id?: number | null } = {}) =>
      request<VisibilityOut>("GET", "/market/visibility", { query }),
    /** Ngày lễ theo nước của tenant (mặc định từ đầu tháng này, 12 tháng). */
    holidays: (query: { start?: string; end?: string } = {}) => request<HolidayOut[]>("GET", "/market/holidays", { query }),
    /** Dự báo thời tiết 5 ngày tại khách sạn của bạn (OpenWeather). */
    weather: () => request<WeatherOut>("GET", "/market/weather"),
    /** Công suất ước tính mới nhất của từng khách sạn theo đêm (≤ 60 đêm). */
    occupancy: (query: { start?: string; end?: string }) =>
      request<MarketOccupancyOut>("GET", "/market/occupancy", { query }),
    /** Khu vực thị trường (toàn thành phố/quận) quét danh sách mọi khách sạn trên Booking. */
    areas: {
      search: (q: string) => request<DestinationOut[]>("GET", "/market/areas/search", { query: { q } }),
      list: () => request<MarketAreaOut[]>("GET", "/market/areas"),
      create: (body: MarketAreaCreate) => request<MarketAreaOut>("POST", "/market/areas", { body }),
      update: (id: number, body: MarketAreaUpdate) => request<MarketAreaOut>("PATCH", `/market/areas/${id}`, { body }),
      remove: (id: number) => request<void>("DELETE", `/market/areas/${id}`),
      scanNow: (id: number) => request<{ area_id: number; enqueued: boolean; list_requested_at: string | null }>("POST", `/market/areas/${id}/scan-now`),
    },
    /** Chỉ báo thị trường cả khu vực cho một đêm (404 khi tenant chưa có khu vực). */
    city: (query: { date?: string; area_id?: number } = {}) => request<MarketCityOut>("GET", "/market/city", { query }),
    cityHotels: (query: { date?: string; area_id?: number; sort?: string; q?: string; limit?: number; offset?: number }) =>
      request<CityHotelsOut>("GET", "/market/city/hotels", { query }),
    events: {
      list: (query: { start?: string; end?: string } = {}) => request<LocalEventOut[]>("GET", "/market/events", { query }),
      create: (body: LocalEventIn) => request<LocalEventOut>("POST", "/market/events", { body }),
      update: (id: number, body: LocalEventIn) => request<LocalEventOut>("PUT", `/market/events/${id}`, { body }),
      remove: (id: number) => request<void>("DELETE", `/market/events/${id}`),
    },
  },
  notifications: {
    settings: () => request<NotificationSettingsOut>("GET", "/notifications/settings"),
    addRecipient: (email: string) => request<RecipientOut>("POST", "/notifications/recipients", { body: { email } }),
    removeRecipient: (id: number) => request<void>("DELETE", `/notifications/recipients/${id}`),
    updateRule: (kind: string, body: { active: boolean; params: Record<string, number> }) =>
      request<NotificationRuleOut>("PUT", `/notifications/rules/${kind}`, { body }),
    /** Gửi email thử tới mọi người nhận (tối đa 1 lần/phút). */
    test: () => request<NotificationLogOut>("POST", "/notifications/test"),
    log: (limit = 30) => request<NotificationLogOut[]>("GET", "/notifications/log", { query: { limit } }),
    /** Ghi nhận "Đã xử lý" một tin trên dashboard. */
    resolve: (id: number) => request<NotificationLogOut>("POST", `/notifications/${id}/resolve`),
    /** Tin gửi/lỗi/bỏ qua, lượt nhấn, "Đã xử lý" và chi phí theo tuần ISO, theo kênh. */
    engagement: (weeks = 8) => request<EngagementOut>("GET", "/notifications/engagement", { query: { weeks } }),
    /** Đăng ký nhận tin theo người: người xem chỉ thấy/sửa của mình; quản trị thấy mọi đăng ký. */
    subscriptions: {
      list: () => request<SubscriptionOut[]>("GET", "/notifications/subscriptions"),
      create: (body: SubscriptionIn) => request<SubscriptionOut>("POST", "/notifications/subscriptions", { body }),
      update: (id: number, body: SubscriptionIn) => request<SubscriptionOut>("PUT", `/notifications/subscriptions/${id}`, { body }),
      remove: (id: number) => request<void>("DELETE", `/notifications/subscriptions/${id}`),
    },
  },
  /** Liên kết tải tệp (thẻ <a>): đi qua proxy `/api`, kèm `tenant_id` cho operator. */
  exports: {
    /** Excel rate shop: khách sạn × đêm (giá, trạng thái, KM, hạn chế, n/N). */
    rateShopUrl: (query: { start?: string; end?: string; price_basis?: PriceBasis }) => apiUrl("/export/rate-shop.xlsx", query),
    /** Báo cáo tháng dạng HTML (mở tab mới, in ra PDF). `month`: "YYYY-MM". */
    monthlyReportUrl: (query: { month?: string; own_hotel_id?: number | null }) => apiUrl("/export/monthly-report.html", query),
  },
  health: {
    summary: () => request<HealthSummaryOut>("GET", "/health/summary"),
    runs: (limit = 20) => request<ScanRunOut[]>("GET", "/health/runs", { query: { limit } }),
    sessions: (limit = 50) => request<ScrapeSessionOut[]>("GET", "/health/sessions", { query: { limit } }),
    /** Operator: quét ngay mọi tenant đang hoạt động. */
    scanNow: () => request<ScanRunOut[]>("POST", "/health/scan-now"),
  },
};
