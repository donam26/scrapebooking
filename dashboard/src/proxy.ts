import { NextResponse, type NextRequest } from "next/server";

/**
 * Chặn mọi trang (trừ trang giới thiệu `/`, ảnh của nó và /login) khi chưa có cookie
 * phiên `sb_session`.
 * Next.js 16 đổi tên `middleware.ts` thành `proxy.ts`; hành vi giữ nguyên.
 * Cookie chỉ được kiểm tra có/không; tính hợp lệ do backend quyết định qua /auth/me
 * (401 -> client tự chuyển về /login).
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (pathname === "/" || pathname === "/login" || pathname.startsWith("/landing/")) return NextResponse.next();
  if (request.cookies.has("sb_session")) return NextResponse.next();
  const login = new URL("/login", request.url);
  login.searchParams.set("next", pathname + search);
  return NextResponse.redirect(login);
}

export const config = {
  // Bỏ qua API proxy, asset tĩnh và favicon.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|robots.txt).*)"],
};
