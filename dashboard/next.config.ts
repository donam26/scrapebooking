import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

// next-intl đọc cấu hình theo request ở src/i18n/request.ts (ngôn ngữ từ cookie, không tiền tố URL).
const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  // Docker: `.next/standalone/server.js` chạy không cần node_modules.
  output: "standalone",
  // Mọi request từ trình duyệt tới /api/* được chuyển tiếp sang backend FastAPI bởi
  // Route Handler `src/app/api/[...path]/route.ts`, đọc API_INTERNAL_URL lúc chạy.
  // Không dùng `rewrites()` vì next.config được serialize lúc build nên env
  // lúc chạy container không có tác dụng.
  poweredByHeader: false,
};

export default withNextIntl(nextConfig);
