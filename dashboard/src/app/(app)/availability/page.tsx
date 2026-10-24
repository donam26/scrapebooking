import { redirect } from "next/navigation";
import { calendarUrl } from "../calendar/redirect-url";

/** Trang Phòng trống cũ: nay là Lịch giá & phòng, cách xem "Phòng còn" (giữ tham số kỳ xem). */
export default async function AvailabilityRedirect({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  redirect(calendarUrl(await searchParams, "rooms"));
}
