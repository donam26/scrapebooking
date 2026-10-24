import { redirect } from "next/navigation";
import { calendarUrl } from "../calendar/redirect-url";

/** Trang Giá & định giá cũ: nay là Lịch giá & phòng, cách xem "Giá" (giữ kỳ xem và cơ sở giá). */
export default async function RatesRedirect({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  redirect(calendarUrl(await searchParams, "rates"));
}
