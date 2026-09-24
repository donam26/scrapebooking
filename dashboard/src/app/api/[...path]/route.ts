import type { NextRequest } from "next/server";

/**
 * Proxy cùng origin: /api/<path> -> ${API_INTERNAL_URL}/<path>.
 *
 * Đọc `process.env.API_INTERNAL_URL` ở mỗi request nên đổi env khi chạy container
 * là đủ, không cần build lại. Cookie httpOnly `sb_session` đi qua nguyên vẹn hai chiều,
 * body (JSON lẫn multipart) được chuyển tiếp nguyên bytes.
 */

export const dynamic = "force-dynamic";

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
]);

function apiBase(): string {
  return (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/+$/, "");
}

type Ctx = { params: Promise<{ path: string[] }> };

async function handle(request: NextRequest, ctx: Ctx): Promise<Response> {
  const { path } = await ctx.params;
  const target = `${apiBase()}/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key)) headers.set(key, value);
  });

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const body = hasBody ? await request.arrayBuffer() : undefined;

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body,
      redirect: "manual",
      cache: "no-store",
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return Response.json(
      { detail: `Không kết nối được API (${apiBase()}): ${message}` },
      { status: 502 },
    );
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
