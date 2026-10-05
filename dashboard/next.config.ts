import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

// next-intl đọc cấu hình theo request ở src/i18n/request.ts (ngôn ngữ từ cookie, không tiền tố URL).
const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

// `next dev` cần eval (React Refresh, source map) và WebSocket HMR; bản build thì không.
const isDev = process.env.NODE_ENV === "development";

/**
 * Content-Security-Policy.
 * - App Router chèn <script> inline (RSC payload, runtime bootstrap) và React đặt style inline
 *   (`style={{…}}`); `headers()` là tĩnh lúc build nên không gắn nonce theo request được → giữ
 *   'unsafe-inline' cho script-src và style-src (vẫn chặn script/style từ origin lạ).
 * - Font qua next/font tự host dưới /_next/static (không cần fonts.googleapis.com / fonts.gstatic.com);
 *   ảnh trang giới thiệu nằm trong public/landing; trình duyệt chỉ gọi API cùng origin (/api/*).
 */
const CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  `connect-src 'self'${isDev ? " ws: wss:" : ""}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: CSP },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "X-Frame-Options", value: "DENY" },
  // Chỉ bật khi reverse proxy đã có TLS. `headers()` được serialize lúc build nên ENABLE_HSTS
  // phải là build arg (không phải env lúc chạy container).
  ...(process.env.ENABLE_HSTS === "1" ? [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }] : []),
];

const nextConfig: NextConfig = {
  // Docker: `.next/standalone/server.js` chạy không cần node_modules.
  output: "standalone",
  // Mọi request từ trình duyệt tới /api/* được chuyển tiếp sang backend FastAPI bởi
  // Route Handler `src/app/api/[...path]/route.ts`, đọc API_INTERNAL_URL lúc chạy.
  // Không dùng `rewrites()` vì next.config được serialize lúc build nên env
  // lúc chạy container không có tác dụng.
  poweredByHeader: false,
  async headers() {
    return [{ source: "/(.*)", headers: SECURITY_HEADERS }];
  },
};

export default withNextIntl(nextConfig);
