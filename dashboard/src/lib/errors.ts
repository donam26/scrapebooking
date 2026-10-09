/**
 * Dịch lỗi của backend sang ngôn ngữ đang chọn khi hiển thị.
 *
 * Backend giữ thông điệp lỗi tiếng Anh ổn định (API/log/test dựa vào đó); mỗi quy tắc dưới đây
 * khớp một thông điệp và trỏ tới khoá trong `messages/<ngôn ngữ>/errors.json`. Thông điệp không
 * khớp quy tắc nào được giữ nguyên. Thêm lỗi mới ở backend: thêm một dòng RULES + khoá ở mọi
 * ngôn ngữ.
 *
 * Dùng trong component: `const errorText = useErrorMessage(); errorText(err)`.
 */

import { useTranslations } from "next-intl";
import { useMemo } from "react";
import type { Messages } from "@/messages";

type ErrorKey = keyof Omit<Messages["errors"], "fields" | "http">;
type FieldKey = keyof Messages["errors"]["fields"];
type Values = Record<string, string>;

export type ErrorsTranslator = ReturnType<typeof useTranslations<"errors">>;

type Rule = [RegExp, ErrorKey, ((m: RegExpMatchArray) => Values)?];

const RULES: Rule[] = [
  // xác thực, phân quyền
  [/^invalid credentials$/, "invalidCredentials"],
  [/^(not authenticated|invalid session)$/, "sessionExpired"],
  [/^user disabled$/, "userDisabled"],
  [/^operator only$/, "operatorOnly"],
  [/^read-only role$/, "readOnlyRole"],
  [/^cannot access another tenant$/, "otherTenant"],
  [/^user has no tenant$/, "userNoTenant"],
  [/^tenant_id is required for operator$/, "pickTenant"],
  [/^tenant_id required$/, "pickTenantForUser"],
  // người dùng
  [/^email already exists$/, "emailExists"],
  [/^user not found$/, "userNotFound"],
  [/^cannot lock or change the role of your own account$/, "selfLock"],
  [/^cannot remove the last active operator$/, "lastOperator"],
  // tenant, lịch quét
  [/^tenant not found$/, "tenantNotFound"],
  [/^unknown timezone '(.+)'.*$/, "unknownTimezone", (m) => ({ value: m[1] })],
  [/^bad time '(.+)'$/, "badTime", (m) => ({ value: m[1] })],
  [/^scan_times must not be empty$/, "scanTimesEmpty"],
  [/^at most (\d+) scan_times per day$/, "scanTimesMax", (m) => ({ max: m[1] })],
  // watchlist, quét
  [/^listing not found$/, "listingNotFound"],
  [/^hotel not in watchlist$/, "hotelNotInWatchlist"],
  [/^hotel not found$/, "hotelNotFound"],
  [/^watchlist is empty$/, "watchlistEmpty"],
  [/^job queue unavailable$/, "queueUnavailable"],
  [/^scan run already created$/, "scanAlreadyCreated"],
  [/^hotel is tracked by other tenants.*$/, "hotelSharedTracked"],
  [/^url already linked to another hotel$/, "urlLinkedElsewhere"],
  [/^duplicate: same hotel #(\d+) on this channel \(id (.+)\)$/, "duplicateListing", (m) => ({ hotel: m[1], id: m[2] })],
  // thị trường toàn thành phố
  [/^proxy not configured$/, "proxyNotConfigured"],
  [/^too many destination searches.*$/, "tooManySearches"],
  [/^booking unreachable.*$/, "bookingUnreachable"],
  [/^at most (\d+) market areas per tenant$/, "marketAreasMax", (m) => ({ max: m[1] })],
  [/^market area already exists$/, "marketAreaExists"],
  [/^market area is inactive$/, "marketAreaInactive"],
  [/^channel paused after blocking.*$/, "channelPaused"],
  [/^only broken listings can be retried$/, "onlyBrokenRetry"],
  [/^hotel has no active listing$/, "noActiveListing"],
  [/^run not found$/, "runNotFound"],
  // thị trường, sự kiện địa phương
  [/^range must be 1–(\d+) nights$/, "rangeNights", (m) => ({ max: m[1] })],
  [/^range must be 1–(\d+) days$/, "rangeDays", (m) => ({ max: m[1] })],
  [/^no such suggestion for this night anymore$/, "suggestionGone"],
  [/^event not found$/, "eventNotFound"],
  [/^market area not found$/, "marketAreaNotFound"],
  [/^(?:Value error, )?end_date before start_date$/, "endBeforeStart"],
  [/^(?:Value error, )?event longer than (\d+) days$/, "eventTooLong", (m) => ({ max: m[1] })],
  // thông báo email
  [/^at most (\d+) recipients$/, "recipientsMax", (m) => ({ max: m[1] })],
  [/^recipient already exists$/, "recipientExists"],
  [/^recipient not found$/, "recipientNotFound"],
  [/^test email sent less than a minute ago$/, "testEmailTooSoon"],
  [/^unknown params for (\w+): (.+)$/, "ruleUnknownParams", (m) => ({ value: m[2] })],
  [/^(\w+) must be an integer$/, "ruleNotInteger"],
  [/^(\w+) must be between (\d+) and (\d+)$/, "ruleRange", (m) => ({ min: m[2], max: m[3] })],
  // đăng ký nhận tin, "Đã xử lý" (Phase 3)
  [/^invalid email$/, "invalidEmail"],
  [/^invalid Vietnamese phone number$/, "invalidPhone"],
  [/^webhook must be https:\/\/$/, "webhookHttps"],
  [/^at most (\d+) subscriptions$/, "subscriptionsMax", (m) => ({ max: m[1] })],
  [/^subscription already exists$/, "subscriptionExists"],
  [/^subscription not found$/, "subscriptionNotFound"],
  [/^not your subscription$/, "notYourSubscription"],
  [/^notification not found$/, "notificationNotFound"],
  // OTB, chiến lược giá, báo cáo (Phase 5–7)
  [/^no own hotel \(role=self\) in watchlist$/, "noOwnHotel"],
  [/^OTB only for role=self hotel$/, "otbSelfOnly"],
  [/^rooms_otb missing or negative$/, "roomsOtbMissing"],
  [/^departure must be after arrival$/, "departureBeforeArrival"],
  [/^(?:Value error, )?floor_price above ceiling_price$/, "floorAboveCeiling"],
  [/^(?:Value error, )?weekday_adj: .*$/, "weekdayAdjRange"],
  [/^month must be YYYY-MM$/, "monthFormat"],
  // tenant
  [/^(?:Value error, )?insight_language must be one of (.+)$/, "reportLanguageInvalid", (m) => ({ value: m[1] })],
  // dữ liệu
  [/^end before start$/, "endBeforeStart"],
  [/^range over (\d+) days$/, "rangeTooLong", (m) => ({ max: m[1] })],
  // bản tin
  [/^insight not found$/, "insightNotFound"],
  [/^no scan data yet.*$/, "noScanData"],
  [/^no json output$/, "noJsonOutput"],
  [/^schema: (.*)$/, "badSchema", (m) => ({ detail: m[1] })],
  [/^timeout: .*$/, "workerTimeout"],
  // proxy /api của Next.js không gọi được backend
  [/^api unreachable .*$/, "apiUnreachable"],
  // PMS
  [/^PMS data only for role=self hotel$/, "pmsSelfOnly"],
  [/^unknown columns (.*)$/, "unknownColumns", (m) => ({ value: m[1] })],
  [/^unknown adapter '(.+)'$/, "unknownAdapter", (m) => ({ value: m[1] })],
  [/^cannot decode file$/, "cannotDecode"],
  [/^empty file or missing header row$/, "emptyFile"],
  [/^empty sheet$/, "emptySheet"],
  [/^cannot read excel: .*$/, "cannotReadExcel"],
  [/^old excel format \(\.xls\) not supported.*$/, "oldExcel"],
  [/^missing mapping for (\w+)$/, "missingMapping", (m) => ({ field: m[1] })],
  [/^unrecognised date '?(.*?)'?$/, "badDate", (m) => ({ value: m[1] })],
  [/^duplicate date (.+)$/, "duplicateDate", (m) => ({ value: m[1] })],
  [/^not a number "?'?(.*?)'?"?$/, "notNumber", (m) => ({ value: m[1] })],
  [/^not an integer "?'?(.*?)'?"?$/, "notInteger", (m) => ({ value: m[1] })],
  [/^sold (\d+) > total (\d+)$/, "soldOverTotal", (m) => ({ sold: m[1], total: m[2] })],
  [/^out of range (.+)$/, "occupancyRange", (m) => ({ value: m[1] })],
  // lỗi kiểm tra dữ liệu của FastAPI/pydantic
  [/^Field required$/, "fieldRequired"],
  [/^String should have at least (\d+) characters?$/, "minLength", (m) => ({ min: m[1] })],
  [/^String should have at most (\d+) characters?$/, "maxLength", (m) => ({ max: m[1] })],
  [/^Input should be greater than or equal to (.+)$/, "gte", (m) => ({ value: m[1] })],
  [/^Input should be greater than (.+)$/, "gt", (m) => ({ value: m[1] })],
  [/^Input should be less than or equal to (.+)$/, "lte", (m) => ({ value: m[1] })],
  [/^value is not a valid email address.*$/, "invalidEmail"],
  [/^String should match pattern .*$/, "invalidValue"],
];

/** Tên trường của lỗi validation (`loc`) theo ngôn ngữ; trường lạ giữ nguyên tên. */
export function fieldLabel(t: ErrorsTranslator, name: string): string {
  const id = `fields.${name}` as `fields.${FieldKey}`;
  return t.has(id) ? t(id) : name;
}

export function translateError(t: ErrorsTranslator, message: string): string {
  const text = message.trim();
  for (const [re, key, values] of RULES) {
    const m = text.match(re);
    if (!m) continue;
    const v = values?.(m) ?? {};
    // Tên trường trong "missing mapping for X" cũng dịch theo ngôn ngữ.
    if (v.field) v.field = fieldLabel(t, v.field);
    return t(key, v);
  }
  return message;
}

type ValidationErrorItem = { loc?: (string | number)[]; msg: string };

/** `detail` của FastAPI (chuỗi hoặc mảng lỗi validation) -> câu đọc được. */
export function detailToMessage(t: ErrorsTranslator, detail: unknown, status?: number): string {
  if (typeof detail === "string" && detail) return translateError(t, detail);
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          const v = item as ValidationErrorItem;
          const loc = (v.loc ?? [])
            .filter((p) => p !== "body" && p !== "query")
            .map((p) => fieldLabel(t, String(p)))
            .join(".");
          const msg = translateError(t, v.msg);
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
  if (status === 401) return t("http.401");
  if (status === 403) return t("http.403");
  if (status === 404) return t("http.404");
  if (status === 502) return t("http.502");
  return status ? t("http.other", { status }) : t("http.unknown");
}

/** Lỗi bất kỳ (ApiError, Error, chuỗi) -> câu theo ngôn ngữ. ApiError nhận diện qua `status`/`detail`. */
export function errorText(t: ErrorsTranslator, err: unknown): string {
  if (err && typeof err === "object" && "status" in err && "detail" in err) {
    const e = err as { status: number; detail: unknown };
    return detailToMessage(t, e.detail, e.status);
  }
  if (err instanceof Error) return translateError(t, err.message);
  return translateError(t, String(err));
}

/** `(err) => câu lỗi` theo ngôn ngữ hiện tại; gọi lúc render để đổi ngôn ngữ là đổi theo. */
export function useErrorMessage(): (err: unknown) => string {
  const t = useTranslations("errors");
  return useMemo(() => (err: unknown) => errorText(t, err), [t]);
}
