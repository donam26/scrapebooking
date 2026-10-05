import { redirect } from "next/navigation";

/** Nhịp đặt phòng nay nằm trong tab Terminal+ (giữ tham số kỳ xem). */
export default async function PaceRedirect({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(await searchParams)) {
    if (typeof v === "string") params.set(k, v);
  }
  const qs = params.toString();
  redirect(`/terminal${qs ? `?${qs}` : ""}#pace`);
}
