import type { NextRequest } from "next/server";
import { DEFAULT_LOCALE, LOCALE_COOKIE, isLocale } from "@/i18n/config";

/**
 * Proxy cùng origin: /api/<path> -> ${API_INTERNAL_URL}/<path>.
 *
 * Đọc `process.env.API_INTERNAL_URL` ở mỗi request nên đổi env khi chạy container
 * là đủ, không cần build lại. Cookie httpOnly `sb_session` đi qua nguyên vẹn hai chiều,
 * body (JSON lẫn multipart) được chuyển tiếp nguyên bytes.
 *
 * Bảo vệ:
 * - Chỉ cho qua các prefix trong ALLOWED_PREFIXES; `/metrics`, `/docs`, `/openapi.json`, `/healthz`…
 *   của backend trả 404 ngay tại đây, không chạm backend.
 * - Body tối đa MAX_BODY_BYTES (413), upstream có timeout (504), lỗi kết nối trả 502 không lộ URL nội bộ.
 * - Không chuyển tiếp `x-forwarded-*`/`forwarded` của client; tự đặt `x-forwarded-for/proto/host`.
 *
 * `Accept-Language` gửi lên backend là ngôn ngữ người dùng chọn (cookie NEXT_LOCALE), không phải
 * ngôn ngữ trình duyệt: backend dịch text nó sinh ra (lý do gợi ý giá, tên ngày lễ, CSV…) theo đó.
 */

export const dynamic = "force-dynamic";

const ALLOWED_PREFIXES = new Set([
  "auth",
  "tenants",
  "settings",
  "users",
  "watchlist",
  "channels",
  "overview",
  "hotels",
  "events",
  "runs",
  "insights",
  "pms",
  "notifications",
  "export",
  "market",
  "health",
]);

/** Xuất CSV và import PMS có thể chạy lâu hơn các request thường. */
const SLOW_PREFIXES = new Set(["export", "pms"]);
const TIMEOUT_MS = 30_000;
const SLOW_TIMEOUT_MS = 60_000;
const MAX_BODY_BYTES = 6 * 1024 * 1024;

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "te",
  "trailer",
  "upgrade",
  "proxy-authorization",
  "proxy-authenticate",
  "host",
  "content-length",
  // fetch đã giải nén body; giữ header này sẽ làm trình duyệt giải nén lần hai.
  "content-encoding",
  // RFC 7239; cùng ý nghĩa với x-forwarded-*, không nhận từ client.
  "forwarded",
]);

function apiBase(): string {
  return (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/+$/, "");
}

function json(status: number, detail: string): Response {
  return Response.json({ detail }, { status });
}

/**
 * Đọc body tối đa `max` byte; vượt thì huỷ stream và trả null (không giữ cả body lớn trong RAM).
 */
async function readBody(request: NextRequest, max: number): Promise<ArrayBuffer | null> {
  const reader = request.body?.getReader();
  if (!reader) return new ArrayBuffer(0);
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > max) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const out = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return out.buffer;
}

type Ctx = { params: Promise<{ path: string[] }> };

async function handle(request: NextRequest, ctx: Ctx): Promise<Response> {
  const { path } = await ctx.params;
  // `..`/`.`/đoạn rỗng sẽ bị URL parser của fetch chuẩn hoá và có thể nhảy ra ngoài allowlist.
  if (path.length === 0 || !ALLOWED_PREFIXES.has(path[0]) || path.some((seg) => seg === "" || seg === "." || seg === "..")) {
    return json(404, "not found");
  }
  const target = `${apiBase()}/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key) && !key.startsWith("x-forwarded-")) headers.set(key, value);
  });
  const chosen = request.cookies.get(LOCALE_COOKIE)?.value;
  headers.set("accept-language", isLocale(chosen) ? chosen : DEFAULT_LOCALE);

  // IP thật do reverse proxy phía trước (Caddy/nginx) đặt; không có thì để trống thay vì bịa.
  const clientIp = request.headers.get("x-forwarded-for") ?? request.headers.get("x-real-ip");
  if (clientIp) headers.set("x-forwarded-for", clientIp);
  headers.set("x-forwarded-proto", request.nextUrl.protocol === "https:" ? "https" : "http");
  const host = request.headers.get("host") ?? request.nextUrl.host;
  if (host) headers.set("x-forwarded-host", host);

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  let body: ArrayBuffer | undefined;
  if (hasBody) {
    const declared = Number(request.headers.get("content-length"));
    if (Number.isFinite(declared) && declared > MAX_BODY_BYTES) return json(413, "request body too large");
    const read = await readBody(request, MAX_BODY_BYTES);
    if (read === null) return json(413, "request body too large");
    body = read;
  }

  const timeoutMs = SLOW_PREFIXES.has(path[0]) ? SLOW_TIMEOUT_MS : TIMEOUT_MS;
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body,
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (err) {
    // Timeout tới dưới dạng DOMException "TimeoutError" (undici); lỗi kết nối là TypeError "fetch failed".
    const name = typeof err === "object" && err !== null && "name" in err ? String(err.name) : "";
    const message = err instanceof Error ? err.message : String(err);
    console.error(`[api proxy] ${request.method} /${path.join("/")}: ${name} ${message}`);
    if (name === "TimeoutError" || name === "AbortError") return json(504, "api timeout");
    return json(502, "api unreachable");
  }

  const resHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key) && key !== "set-cookie") resHeaders.set(key, value);
  });
  for (const cookie of upstream.headers.getSetCookie()) resHeaders.append("set-cookie", cookie);

  return new Response(upstream.status === 204 ? null : upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: resHeaders,
  });
}

export { handle as GET, handle as POST, handle as PUT, handle as PATCH, handle as DELETE };
