import { redirect } from "next/navigation";

/** Trang Tổng quan cũ: nay là tab Phòng trống (giữ nguyên tham số kỳ xem và kênh). */
export default async function OverviewRedirect({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(await searchParams)) {
    if (typeof v === "string") params.set(k, v);
  }
  const qs = params.toString();
  redirect(qs ? `/availability?${qs}` : "/availability");
}
