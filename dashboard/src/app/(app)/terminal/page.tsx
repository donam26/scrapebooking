import { redirect } from "next/navigation";

/** Terminal+ đã tách (Q5): phần khu vực sang Thị trường (/market), nhịp đặt phòng sang Báo cáo. Giữ query. */
export default async function TerminalRedirect({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(await searchParams)) {
    if (typeof v === "string") params.set(k, v);
  }
  const qs = params.toString();
  redirect(`/market${qs ? `?${qs}` : ""}`);
}
