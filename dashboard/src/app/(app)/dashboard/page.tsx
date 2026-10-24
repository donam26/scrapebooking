import { redirect } from "next/navigation";

/** Bảng điều khiển cũ: nay gộp vào Hôm nay (giữ tham số `hotel`). */
export default async function DashboardRedirect({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = new URLSearchParams();
  const hotel = (await searchParams).hotel;
  if (typeof hotel === "string") params.set("hotel", hotel);
  const qs = params.toString();
  redirect(qs ? `/today?${qs}` : "/today");
}
