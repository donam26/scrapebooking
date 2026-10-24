/**
 * URL của Lịch giá & phòng từ tham số của trang cũ (/availability, /rates, /overview): giữ mọi tham
 * số, đặt `view` khi trang cũ tương ứng một cách xem.
 */
export function calendarUrl(searchParams: Record<string, string | string[] | undefined>, view?: "rooms" | "rates"): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(searchParams)) {
    if (typeof v === "string") params.set(k, v);
  }
  if (view) params.set("view", view);
  const qs = params.toString();
  return qs ? `/calendar?${qs}` : "/calendar";
}
